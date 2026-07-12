"""Rate limiting middleware STUB.

Story E2 replaces the body with a Redis token bucket.
AGENTS.md rule 8: this wrapper must remain in the request path — do not remove.
"""
from fastapi import Request


async def rate_limit_middleware(request: Request, call_next):
    # TODO(E2): Redis token bucket per API key / IP; 429 + Retry-After on exceed.
    return await call_next(request)
