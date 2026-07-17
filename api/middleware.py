"""Rate limiting middleware — Redis token bucket (story E2).

AGENTS.md rule 8: this wrapper must remain in the request path — do not remove.
"""
import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from api.rate_limit import check_rate_limit, client_ip, rate_limit_headers

logger = logging.getLogger(__name__)


async def rate_limit_middleware(request: Request, call_next):
    redis = getattr(request.app.state, "redis", None)
    script_sha = getattr(request.app.state, "rate_limit_script_sha", None)
    ip = client_ip(dict(request.headers), request.client.host if request.client else None)

    result = await check_rate_limit(
        redis,
        script_sha,
        method=request.method,
        path=request.url.path,
        authorization=request.headers.get("Authorization"),
        ip=ip,
    )

    if result is not None and not result.allowed:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers=rate_limit_headers(result),
        )

    response = await call_next(request)
    if result is not None:
        for key, value in rate_limit_headers(result).items():
            response.headers[key] = value
    return response
