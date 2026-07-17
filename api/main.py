"""Perzforge API entrypoint.

Run: uvicorn api.main:app --reload
"""
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

import api.queue as queue
from api.config import settings
from api.middleware import rate_limit_middleware
from api.quotas import QuotaExceededError
from api.rate_limit import register_script
from api.routers import admin, auth, job_logs, jobs, keys, quotas, scope_probe


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    owned_redis = False
    redis = getattr(app.state, "redis", None)
    if redis is None:
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        app.state.redis = redis
        queue.set_redis_client(redis)
        owned_redis = True
    if not getattr(app.state, "rate_limit_script_sha", None):
        app.state.rate_limit_script_sha = await register_script(redis)
    try:
        yield
    finally:
        if owned_redis:
            queue.set_redis_client(None)
            app.state.redis = None
            app.state.rate_limit_script_sha = None
            await redis.aclose()


app = FastAPI(
    title="Perzforge",
    version="0.1.0",
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan,
)

app.middleware("http")(rate_limit_middleware)


@app.exception_handler(QuotaExceededError)
async def quota_exceeded_handler(_request: Request, exc: QuotaExceededError) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "detail": exc.detail,
            "quota": exc.quota,
            "limit": exc.limit,
            "current": exc.current,
        },
    )


@app.get("/api/v1/healthz")
async def healthz():
    # public: infrastructure liveness probe, returns no data
    return {"status": "ok", "service": "perzforge"}


app.include_router(auth.router, prefix="/api/v1")
app.include_router(keys.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(quotas.admin_quota_router, prefix="/api/v1")
app.include_router(quotas.me_router, prefix="/api/v1")
app.include_router(jobs.router, prefix="/api/v1")
app.include_router(job_logs.router, prefix="/api/v1")
app.include_router(scope_probe.router, prefix="/api/v1")
