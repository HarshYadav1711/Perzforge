"""Perzforge API entrypoint.

Run: uvicorn api.main:app --reload
"""
from fastapi import FastAPI

from api.middleware import rate_limit_middleware
from api.routers import admin, auth, job_logs, jobs, keys, scope_probe

app = FastAPI(
    title="Perzforge",
    version="0.1.0",
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
)

app.middleware("http")(rate_limit_middleware)


@app.get("/api/v1/healthz")
async def healthz():
    # public: infrastructure liveness probe, returns no data
    return {"status": "ok", "service": "perzforge"}


app.include_router(auth.router, prefix="/api/v1")
app.include_router(keys.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(jobs.router, prefix="/api/v1")
app.include_router(job_logs.router, prefix="/api/v1")
app.include_router(scope_probe.router, prefix="/api/v1")
