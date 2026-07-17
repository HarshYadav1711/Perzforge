"""Redis token-bucket rate limiting (story E2)."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import jwt
from redis.asyncio import Redis
from redis.exceptions import NoScriptError, RedisError

from api.config import settings
from api.security import is_api_key_token

logger = logging.getLogger(__name__)

# Atomic token bucket: refill by elapsed time, then try to consume `cost` tokens.
# Returns: {allowed, remaining, limit, retry_after_seconds, reset_unix}
TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local now_ms = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])

local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])

if tokens == nil or ts == nil then
  tokens = capacity
  ts = now_ms
end

local elapsed = (now_ms - ts) / 1000.0
if elapsed < 0 then
  elapsed = 0
end
tokens = math.min(capacity, tokens + (elapsed * rate))
ts = now_ms

local allowed = 0
local retry_after = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
else
  retry_after = math.ceil((cost - tokens) / rate)
  if retry_after < 1 then
    retry_after = 1
  end
end

redis.call('HSET', key, 'tokens', tokens, 'ts', ts)
local ttl_ms = math.ceil((capacity / rate) * 2000)
if ttl_ms < 1000 then
  ttl_ms = 1000
end
redis.call('PEXPIRE', key, ttl_ms)

local remaining = math.floor(tokens)
local reset_unix = math.floor(now_ms / 1000) + math.ceil((capacity - tokens) / rate)
return {allowed, remaining, capacity, retry_after, reset_unix}
"""


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    name: str
    rate_per_second: float
    burst: int
    force_ip: bool = False


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int
    reset_unix: int


def default_policy() -> RateLimitPolicy:
    return RateLimitPolicy(
        name="default",
        rate_per_second=settings.rate_limit_default_per_min / 60.0,
        burst=settings.rate_limit_default_burst,
    )


def auth_policy() -> RateLimitPolicy:
    return RateLimitPolicy(
        name="auth",
        rate_per_second=settings.rate_limit_auth_per_min / 60.0,
        burst=settings.rate_limit_auth_burst,
        force_ip=True,
    )


def jobs_write_policy() -> RateLimitPolicy:
    return RateLimitPolicy(
        name="jobs_write",
        rate_per_second=settings.rate_limit_jobs_write_per_hour / 3600.0,
        burst=settings.rate_limit_jobs_write_burst,
    )


def llm_policy() -> RateLimitPolicy:
    return RateLimitPolicy(
        name="llm",
        rate_per_second=settings.rate_limit_llm_per_min / 60.0,
        burst=settings.rate_limit_llm_burst,
    )


@dataclass(frozen=True, slots=True)
class RouteRule:
    methods: frozenset[str]
    path: str
    match: str  # "exact" | "prefix"
    policy_factory: Any


# Central route→tier registry (not scattered path checks).
ROUTE_RULES: tuple[RouteRule, ...] = (
    RouteRule(
        methods=frozenset({"POST"}),
        path="/api/v1/auth/login",
        match="exact",
        policy_factory=auth_policy,
    ),
    RouteRule(
        methods=frozenset({"POST"}),
        path="/api/v1/auth/refresh",
        match="exact",
        policy_factory=auth_policy,
    ),
    RouteRule(
        methods=frozenset({"POST"}),
        path="/api/v1/jobs",
        match="exact",
        policy_factory=jobs_write_policy,
    ),
    RouteRule(
        methods=frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"}),
        path="/api/v1/llm",
        match="prefix",
        policy_factory=llm_policy,
    ),
)


def resolve_policy(method: str, path: str) -> RateLimitPolicy:
    normalized = path.rstrip("/") or "/"
    method_upper = method.upper()
    for rule in ROUTE_RULES:
        if method_upper not in rule.methods:
            continue
        rule_path = rule.path.rstrip("/") or "/"
        if rule.match == "exact" and normalized == rule_path:
            return rule.policy_factory()
        if rule.match == "prefix" and (
            normalized == rule_path or normalized.startswith(rule_path + "/")
        ):
            return rule.policy_factory()
    return default_policy()


def is_exempt_path(path: str) -> bool:
    normalized = path.rstrip("/") or "/"
    return normalized in {"/api/v1/healthz", "/healthz"}


def client_ip(headers: dict[str, str], client_host: str | None) -> str:
    forwarded = headers.get("x-forwarded-for") or headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip() or (client_host or "unknown")
    return client_host or "unknown"


def resolve_identity(
    *,
    authorization: str | None,
    ip: str,
    force_ip: bool,
) -> str:
    if force_ip:
        return f"ip:{ip}"

    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if token:
            if is_api_key_token(token):
                # API key prefix isolates buckets without hashing the full secret.
                return f"key:{token[:8]}"
            try:
                payload = jwt.decode(
                    token,
                    settings.jwt_secret,
                    algorithms=["HS256"],
                    options={"verify_exp": False},
                )
                sub = payload.get("sub")
                if sub:
                    return f"user:{sub}"
            except jwt.PyJWTError:
                pass

    return f"ip:{ip}"


def bucket_key(policy_name: str, identity: str) -> str:
    return f"perzforge:ratelimit:{policy_name}:{identity}"


async def register_script(redis: Redis) -> str:
    return await redis.script_load(TOKEN_BUCKET_LUA)


async def consume_token(
    redis: Redis,
    script_sha: str,
    *,
    policy: RateLimitPolicy,
    identity: str,
) -> RateLimitResult:
    key = bucket_key(policy.name, identity)
    now_ms = int(time.time() * 1000)
    args = [
        str(policy.burst),
        str(policy.rate_per_second),
        str(now_ms),
        "1",
    ]
    try:
        raw = await redis.evalsha(script_sha, 1, key, *args)
    except NoScriptError:
        sha = await register_script(redis)
        raw = await redis.evalsha(sha, 1, key, *args)
    allowed, remaining, limit, retry_after, reset_unix = (int(v) for v in raw)
    return RateLimitResult(
        allowed=bool(allowed),
        limit=limit,
        remaining=max(0, remaining),
        retry_after=max(0, retry_after),
        reset_unix=reset_unix,
    )


def rate_limit_headers(result: RateLimitResult) -> dict[str, str]:
    headers = {
        "X-RateLimit-Limit": str(result.limit),
        "X-RateLimit-Remaining": str(result.remaining),
        "X-RateLimit-Reset": str(result.reset_unix),
    }
    if not result.allowed:
        headers["Retry-After"] = str(result.retry_after)
    return headers


async def check_rate_limit(
    redis: Redis | None,
    script_sha: str | None,
    *,
    method: str,
    path: str,
    authorization: str | None,
    ip: str,
) -> RateLimitResult | None:
    """Return a result, or None when limiting is skipped (exempt / fail-open)."""
    if is_exempt_path(path):
        return None
    if redis is None or not script_sha:
        logger.warning("rate limit skipped: redis unavailable (fail-open)")
        return None

    policy = resolve_policy(method, path)
    identity = resolve_identity(
        authorization=authorization,
        ip=ip,
        force_ip=policy.force_ip,
    )
    try:
        return await consume_token(redis, script_sha, policy=policy, identity=identity)
    except (RedisError, ConnectionError, OSError, TimeoutError):
        logger.warning(
            "rate limit Redis error — failing open for %s %s",
            method,
            path,
            exc_info=True,
        )
        return None
