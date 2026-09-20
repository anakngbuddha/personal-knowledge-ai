"""Authentication and principal inspection routes for Phase 0."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.security.deps import get_or_create_default_org, resolve_principal
from app.security.jwt import mint_token
from app.security.labels import Role, normalize
from app.security.principal import Principal

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenRequest(BaseModel):
    org_id: str | None = None
    user_id: str | None = None
    role: str = Role.SOLUTIONS_ENGINEER


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    org_id: str
    user_id: str | None
    role: str


@router.post("/token", response_model=TokenResponse)
def issue_token(
    payload: TokenRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Issue a signed cryptographic JWT for API access."""
    if payload.org_id:
        target_org_id = uuid.UUID(payload.org_id)
    else:
        default_org = get_or_create_default_org(db)
        target_org_id = default_org.id
    target_user_id = uuid.UUID(payload.user_id) if payload.user_id else None

    try:
        validated_role = normalize(payload.role, Role, Role.VIEWER)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    token = mint_token(
        org_id=target_org_id,
        user_id=target_user_id,
        role=validated_role,
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in_seconds=settings.jwt_access_token_expire_minutes * 60,
        org_id=str(target_org_id),
        user_id=str(target_user_id) if target_user_id else None,
        role=validated_role,
    )


@router.get("/me")
def get_current_principal_profile(
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    """Inspect the authenticated principal, tenant context, and role capabilities."""
    info = principal.describe()
    info.update(
        {
            "is_owner": principal.is_owner,
            "is_admin": principal.is_admin,
            "can_write_catalog": principal.can_write_catalog,
            "can_manage_users": principal.can_manage_users,
            "can_export_restricted": principal.can_export_restricted,
            "readable_sensitivities": principal.readable_sensitivities(),
        }
    )
    return info
