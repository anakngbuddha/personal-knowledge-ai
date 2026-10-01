"""Administrator-defined retention; all deletion is disabled until configured."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.security.deps import resolve_principal
from app.security.principal import Principal
from app.security import retention
from app.core.errors import AppError
from app.storage.factory import get_storage

router = APIRouter(prefix="/ops/retention", tags=["operations"])

class PolicyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    periods: dict[str, StrictInt] = Field(default_factory=dict, max_length=5)
    enabled: StrictBool = False
    legal_hold: StrictBool = False

class HoldIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(max_length=32)
    resource_id: uuid.UUID

class PurgeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dry_run: StrictBool = True
    batch_size: int = Field(100, ge=1, le=500)

def _call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except AppError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc

@router.get("/policy")
def get_policy(db: Session = Depends(get_db), principal: Principal = Depends(resolve_principal)):
    _call(retention.require_admin, principal)
    policy = db.get(retention.RetentionPolicy, principal.org_id)
    return {"enabled": policy.enabled, "legal_hold": policy.legal_hold, "periods": policy.periods} if policy else {"enabled": False, "legal_hold": False, "periods": {}}

@router.put("/policy")
def configure_policy(payload: PolicyIn, db: Session = Depends(get_db), principal: Principal = Depends(resolve_principal)):
    policy = _call(retention.set_policy, db, principal, **payload.model_dump())
    return {"enabled": policy.enabled, "legal_hold": policy.legal_hold, "periods": policy.periods}

@router.post("/holds", status_code=201)
def place_hold(payload: HoldIn, db: Session = Depends(get_db), principal: Principal = Depends(resolve_principal)):
    hold = _call(retention.add_hold, db, principal, payload.kind, payload.resource_id)
    return {"id": str(hold.id), "kind": hold.kind, "resource_id": str(hold.resource_id)}

@router.post("/purge")
def preview_or_purge(payload: PurgeIn, db: Session = Depends(get_db), principal: Principal = Depends(resolve_principal)):
    return _call(retention.purge, db, principal, **payload.model_dump())

@router.post("/object-cleanup")
def cleanup_objects(payload: PurgeIn, db: Session = Depends(get_db), principal: Principal = Depends(resolve_principal)):
    _call(retention.require_admin, principal)
    if payload.dry_run:
        return {"dry_run": True, "deleted": 0}
    return _call(retention.drain_object_deletions, db, principal, get_storage(), batch_size=payload.batch_size)

@router.get("/orphans")
def inspect_orphans(workspace_id: uuid.UUID, limit: int = Query(100, ge=1, le=500), cursor: str | None = Query(None, max_length=2048), db: Session = Depends(get_db), principal: Principal = Depends(resolve_principal)):
    return _call(retention.orphan_inventory, db, principal, get_storage(), workspace_id, cursor=cursor, limit=limit)
