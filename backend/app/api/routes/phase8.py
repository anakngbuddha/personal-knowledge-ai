"""Strict, tenant-scoped start endpoints for Phase 8 playbooks."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.routes.workflows import _get_run, _require_approver, _run_out, start_playbook_run
from app.db.session import get_db
from app.security.deps import resolve_principal
from app.security.principal import Principal
from app.workflows.schemas import WorkflowRunOut

router = APIRouter(prefix="/workflows", tags=["workflows"])


class DiscoveryNotesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notes: Annotated[str, Field(min_length=1, max_length=50_000)]
    account_ref: Annotated[str | None, Field(default=None, max_length=128)]


class IncidentTriageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    logs: Annotated[str, Field(min_length=1, max_length=50_000)]
    install_base: Annotated[list[str], Field(min_length=1, max_length=100)]
    account_ref: Annotated[str | None, Field(default=None, max_length=128)]


class UpgradeImpactIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product: Annotated[str, Field(min_length=1, max_length=512)]
    proposed_version: Annotated[str | None, Field(default=None, max_length=128)]


def _start(db: Session, principal: Principal, slug: str, payload: BaseModel) -> WorkflowRunOut:
    _require_approver(principal)
    run = start_playbook_run(db, principal, slug, payload.model_dump())
    return _run_out(_get_run(db, run.id, principal.org_id) or run)


@router.post("/solution-composer/run", response_model=WorkflowRunOut)
def start_solution_composer(
    payload: DiscoveryNotesIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> WorkflowRunOut:
    return _start(db, principal, "solution-composer", payload)


@router.post("/incident-triage/run", response_model=WorkflowRunOut)
def start_incident_triage(
    payload: IncidentTriageIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> WorkflowRunOut:
    return _start(db, principal, "incident-triage", payload)


@router.post("/upgrade-impact/run", response_model=WorkflowRunOut)
def start_upgrade_impact(
    payload: UpgradeImpactIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> WorkflowRunOut:
    return _start(db, principal, "upgrade-impact", payload)
