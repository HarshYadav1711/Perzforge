"""Internal scope probe routes for integration testing until job routes ship."""
from fastapi import APIRouter, Depends

from api.deps import Principal, require_scopes

router = APIRouter(prefix="/test/scope-probe", tags=["scope-probe"], include_in_schema=False)


@router.get("/jobs-read")
async def probe_jobs_read(
    principal: Principal = Depends(require_scopes("jobs:read")),
):
    return {"status": "ok", "user_id": str(principal.user.id)}


@router.post("/jobs-write")
async def probe_jobs_write(
    principal: Principal = Depends(require_scopes("jobs:write")),
):
    return {"status": "ok", "user_id": str(principal.user.id)}
