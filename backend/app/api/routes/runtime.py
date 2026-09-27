"""GET /ops/runtime: contention metrics for operators (audit findings 7 and 8)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.ops.runtime_metrics import snapshot
from app.security.deps import resolve_principal
from app.security.principal import Principal

router = APIRouter(prefix="/ops", tags=["ops"])


@router.get("/runtime")
async def runtime_metrics(principal: Principal = Depends(resolve_principal)) -> dict:
    if not principal.is_admin:
        raise HTTPException(status_code=403, detail="admin role required")
    return snapshot()
