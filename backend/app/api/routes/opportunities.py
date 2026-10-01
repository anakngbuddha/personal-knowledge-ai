"""Tenant-scoped opportunity and requirement coverage API."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.db.models import (
    Opportunity, OpportunityParticipant, OpportunityRequirement, SalesAccount, Workspace,
)
from app.db.session import get_db
from app.documents.service import get_or_create_default_workspace
from app.playbooks.rfp import heuristic_requirements
from app.security.audit import record_audit
from app.security.accounts import OrganizationMembership
from app.security.deps import resolve_principal
from app.security.labels import Role, role_has_access
from app.security.principal import Principal

router = APIRouter(prefix="/api", tags=["opportunities"])


class AccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    external_system: str | None = Field(default=None, max_length=64)
    external_id: str | None = Field(default=None, max_length=255)


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    external_system: str | None
    external_id: str | None


class OpportunityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    account_id: uuid.UUID | None = None
    workspace_id: uuid.UUID | None = None
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")


class OpportunityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID | None
    workspace_id: uuid.UUID
    owner_id: uuid.UUID | None
    title: str
    stage: str
    currency: str
    version: int
    created_at: datetime


class OpportunityListOut(BaseModel):
    items: list[OpportunityOut]
    limit: int
    offset: int


class RequirementCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_text: str = Field(min_length=1, max_length=10000)
    acceptance_criterion: str | None = Field(default=None, max_length=10000)
    priority: str = Field(default="must", pattern=r"^(must|should|could)$")


class RequirementsImportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=100000)


class RequirementsImportOut(BaseModel):
    created: int
    requirements: list[RequirementOut]


class RequirementUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    acceptance_criterion: str | None = Field(default=None, max_length=10000)
    coverage_state: str = Field(pattern=r"^(unreviewed|covered|partial|gap|excluded)$")
    coverage_note: str | None = Field(default=None, max_length=10000)


class RequirementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    opportunity_id: uuid.UUID
    original_text: str
    acceptance_criterion: str | None
    priority: str
    coverage_state: str
    coverage_note: str | None
    reviewer_id: uuid.UUID | None
    version: int


class ParticipantGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    access: str = Field(pattern=r"^(read|edit)$")


class ParticipantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    access: str


class CoverageOut(BaseModel):
    opportunity_id: uuid.UUID
    requirements: list[RequirementOut]
    total: int
    limit: int
    offset: int
    mandatory_total: int
    mandatory_covered: int
    ready_for_quote: bool


def _require_sales(principal: Principal) -> None:
    if not role_has_access(principal.role, Role.SALES):
        raise HTTPException(403, "sales role required")
    if principal.user_id is None and not principal.is_admin:
        raise HTTPException(403, "an identified user is required")


def _visible_opportunity(
    db: Session, principal: Principal, opportunity_id: uuid.UUID, *, write: bool = False
) -> Opportunity:
    statement = select(Opportunity).where(
        Opportunity.id == opportunity_id, Opportunity.org_id == principal.org_id
    )
    opportunity = db.scalars(statement).first()
    if opportunity is None:
        raise HTTPException(404, "opportunity not found")
    if not principal.is_admin and (principal.user_id is None or opportunity.owner_id != principal.user_id):
        participant = db.scalars(
            select(OpportunityParticipant).where(
                OpportunityParticipant.org_id == principal.org_id,
                OpportunityParticipant.opportunity_id == opportunity_id,
                OpportunityParticipant.user_id == principal.user_id,
            )
        ).first() if principal.user_id is not None else None
        if participant is None or (write and participant.access != "edit"):
            raise HTTPException(404, "opportunity not found")
    return opportunity


@router.post("/accounts", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
def create_account(
    payload: AccountCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> AccountOut:
    _require_sales(principal)
    if bool(payload.external_system) != bool(payload.external_id):
        raise HTTPException(422, "external system and ID must be provided together")
    account = SalesAccount(org_id=principal.org_id, **payload.model_dump())
    db.add(account)
    db.commit()
    db.refresh(account)
    record_audit(db, principal, "create", "sales_account", str(account.id))
    return AccountOut.model_validate(account)


@router.post("/opportunities", response_model=OpportunityOut, status_code=status.HTTP_201_CREATED)
def create_opportunity(
    payload: OpportunityCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> OpportunityOut:
    _require_sales(principal)
    if payload.workspace_id:
        workspace = db.scalars(
            select(Workspace).where(
                Workspace.id == payload.workspace_id, Workspace.org_id == principal.org_id
            )
        ).first()
        if workspace is None:
            raise HTTPException(404, "workspace not found")
    else:
        workspace = get_or_create_default_workspace(db, principal.org_id)
    if payload.account_id:
        account = db.scalars(
            select(SalesAccount).where(
                SalesAccount.id == payload.account_id, SalesAccount.org_id == principal.org_id
            )
        ).first()
        if account is None:
            raise HTTPException(404, "account not found")
    opportunity = Opportunity(
        org_id=principal.org_id,
        workspace_id=workspace.id,
        account_id=payload.account_id,
        owner_id=principal.user_id,
        title=payload.title.strip(),
        currency=payload.currency,
    )
    db.add(opportunity)
    db.commit()
    db.refresh(opportunity)
    record_audit(db, principal, "create", "opportunity", str(opportunity.id))
    return OpportunityOut.model_validate(opportunity)


@router.get("/opportunities", response_model=OpportunityListOut)
def list_opportunities(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> OpportunityListOut:
    statement = select(Opportunity).where(Opportunity.org_id == principal.org_id)
    if not principal.is_admin:
        if principal.user_id is None:
            return OpportunityListOut(items=[], limit=limit, offset=offset)
        shared = select(OpportunityParticipant.opportunity_id).where(
            OpportunityParticipant.org_id == principal.org_id,
            OpportunityParticipant.user_id == principal.user_id,
        )
        statement = statement.where(or_(
            Opportunity.owner_id == principal.user_id, Opportunity.id.in_(shared)
        ))
    rows = db.scalars(statement.order_by(Opportunity.created_at.desc(), Opportunity.id).limit(limit).offset(offset))
    return OpportunityListOut(
        items=[OpportunityOut.model_validate(row) for row in rows], limit=limit, offset=offset
    )


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityOut)
def get_opportunity(
    opportunity_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> OpportunityOut:
    return OpportunityOut.model_validate(_visible_opportunity(db, principal, opportunity_id))


@router.post(
    "/opportunities/{opportunity_id}/participants",
    response_model=ParticipantOut,
    status_code=status.HTTP_201_CREATED,
)
def grant_participant(
    opportunity_id: uuid.UUID,
    payload: ParticipantGrant,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> ParticipantOut:
    _require_sales(principal)
    opportunity = _visible_opportunity(db, principal, opportunity_id)
    if not principal.is_admin and opportunity.owner_id != principal.user_id:
        raise HTTPException(403, "only the owner can share an opportunity")
    membership = db.scalars(select(OrganizationMembership).where(
        OrganizationMembership.org_id == principal.org_id,
        OrganizationMembership.user_id == payload.user_id,
        OrganizationMembership.is_active.is_(True),
    )).first()
    if membership is None:
        raise HTTPException(404, "organization member not found")
    row = db.scalars(select(OpportunityParticipant).where(
        OpportunityParticipant.org_id == principal.org_id,
        OpportunityParticipant.opportunity_id == opportunity_id,
        OpportunityParticipant.user_id == payload.user_id,
    )).first()
    if row is None:
        row = OpportunityParticipant(
            org_id=principal.org_id, opportunity_id=opportunity_id,
            user_id=payload.user_id, access=payload.access,
        )
        db.add(row)
    else:
        row.access = payload.access
    db.commit()
    db.refresh(row)
    record_audit(db, principal, "grant", "opportunity_participant", str(row.id),
                 {"access": row.access, "user_id": str(row.user_id)})
    return ParticipantOut.model_validate(row)


@router.post(
    "/opportunities/{opportunity_id}/requirements",
    response_model=RequirementOut,
    status_code=status.HTTP_201_CREATED,
)
def create_requirement(
    opportunity_id: uuid.UUID,
    payload: RequirementCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> RequirementOut:
    _require_sales(principal)
    _visible_opportunity(db, principal, opportunity_id, write=True)
    requirement = OpportunityRequirement(
        org_id=principal.org_id,
        opportunity_id=opportunity_id,
        original_text=payload.original_text.strip(),
        acceptance_criterion=payload.acceptance_criterion,
        priority=payload.priority,
    )
    db.add(requirement)
    db.commit()
    db.refresh(requirement)
    record_audit(db, principal, "create", "opportunity_requirement", str(requirement.id))
    return RequirementOut.model_validate(requirement)


@router.post(
    "/opportunities/{opportunity_id}/requirements/import",
    response_model=RequirementsImportOut,
    status_code=status.HTTP_201_CREATED,
)
def import_requirements(
    opportunity_id: uuid.UUID,
    payload: RequirementsImportIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> RequirementsImportOut:
    _require_sales(principal)
    _visible_opportunity(db, principal, opportunity_id, write=True)
    parsed = heuristic_requirements(payload.text)
    if not parsed:
        raise HTTPException(422, "no mandatory requirements found; add requirements manually")
    if len(parsed) > 100:
        raise HTTPException(422, "import supports at most 100 requirements at a time")
    rows = [OpportunityRequirement(
        org_id=principal.org_id,
        opportunity_id=opportunity_id,
        original_text=row["text"],
        priority="must",
    ) for row in parsed]
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)
    record_audit(db, principal, "import", "opportunity_requirements", str(opportunity_id),
                 {"count": len(rows)})
    return RequirementsImportOut(
        created=len(rows), requirements=[RequirementOut.model_validate(row) for row in rows]
    )


@router.patch(
    "/opportunities/{opportunity_id}/requirements/{requirement_id}",
    response_model=RequirementOut,
)
def update_requirement(
    opportunity_id: uuid.UUID,
    requirement_id: uuid.UUID,
    payload: RequirementUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> RequirementOut:
    _require_sales(principal)
    _visible_opportunity(db, principal, opportunity_id, write=True)
    requirement = db.scalars(
        select(OpportunityRequirement).where(
            OpportunityRequirement.id == requirement_id,
            OpportunityRequirement.opportunity_id == opportunity_id,
            OpportunityRequirement.org_id == principal.org_id,
        )
    ).first()
    if requirement is None:
        raise HTTPException(404, "requirement not found")
    if requirement.version != payload.version:
        raise HTTPException(409, "requirement was changed; reload before editing")
    if payload.coverage_state != "unreviewed" and not payload.coverage_note:
        raise HTTPException(422, "coverage note is required for a reviewed decision")
    result = db.execute(
        update(OpportunityRequirement)
        .where(
            OpportunityRequirement.id == requirement_id,
            OpportunityRequirement.opportunity_id == opportunity_id,
            OpportunityRequirement.org_id == principal.org_id,
            OpportunityRequirement.version == payload.version,
        )
        .values(
            acceptance_criterion=payload.acceptance_criterion,
            coverage_state=payload.coverage_state,
            coverage_note=payload.coverage_note,
            reviewer_id=principal.user_id,
            version=payload.version + 1,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "requirement was changed; reload before editing")
    db.commit()
    db.refresh(requirement)
    record_audit(db, principal, "update", "opportunity_requirement", str(requirement.id))
    return RequirementOut.model_validate(requirement)


@router.get("/opportunities/{opportunity_id}/coverage", response_model=CoverageOut)
def get_coverage(
    opportunity_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> CoverageOut:
    _visible_opportunity(db, principal, opportunity_id)
    base = (
        OpportunityRequirement.org_id == principal.org_id,
        OpportunityRequirement.opportunity_id == opportunity_id,
    )
    total = db.scalar(select(func.count()).select_from(OpportunityRequirement).where(*base)) or 0
    mandatory_total = db.scalar(
        select(func.count()).select_from(OpportunityRequirement).where(
            *base, OpportunityRequirement.priority == "must"
        )
    ) or 0
    mandatory_covered = db.scalar(
        select(func.count()).select_from(OpportunityRequirement).where(
            *base,
            OpportunityRequirement.priority == "must",
            OpportunityRequirement.coverage_state == "covered",
        )
    ) or 0
    rows = list(db.scalars(
        select(OpportunityRequirement).where(*base)
        .order_by(OpportunityRequirement.created_at, OpportunityRequirement.id)
        .limit(limit).offset(offset)
    ))
    return CoverageOut(
        opportunity_id=opportunity_id,
        requirements=[RequirementOut.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
        mandatory_total=mandatory_total,
        mandatory_covered=mandatory_covered,
        ready_for_quote=bool(total) and mandatory_covered == mandatory_total,
    )
