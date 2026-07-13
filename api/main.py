"""Perzforge API entrypoint.

Run: uvicorn api.main:app --reload
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.middleware import rate_limit_middleware
from api.quotas import QuotaExceededError
from api.routers import admin, auth, job_logs, jobs, keys, quotas, scope_probe

app = FastAPI(
    title="Perzforge",
    version="0.1.0",
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
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
