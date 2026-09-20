"""Tests for Phase 0 cryptographic JWT authentication and role hierarchy."""

from __future__ import annotations

import time
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.models import AccessGrant, Base, Organization
from app.db.session import get_db
from app.main import app
from app.security.jwt import (
    InvalidTokenError,
    TokenExpiredError,
    create_jwt,
    decode_jwt,
    mint_token,
)
from app.security.labels import Role, role_has_access, role_rank

client = TestClient(app)


@pytest.fixture(autouse=True)
def mock_db_session():
    """Ensure tests run against a shared in-memory SQLite database without needing PostgreSQL."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine, tables=[Organization.__table__, AccessGrant.__table__]
    )
    SessionClass = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = SessionClass()
    org = Organization(
        slug=settings.default_org_slug, name=settings.default_org_name
    )
    session.add(org)
    session.commit()

    def _get_test_db():
        test_session = SessionClass()
        try:
            yield test_session
        finally:
            test_session.close()

    app.dependency_overrides[get_db] = _get_test_db
    try:
        yield session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def test_jwt_encode_and_decode_valid():
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    token = mint_token(org_id=org_id, user_id=user_id, role=Role.ADMIN)

    payload = decode_jwt(token)
    assert payload["org_id"] == str(org_id)
    assert payload["sub"] == str(user_id)
    assert payload["role"] == Role.ADMIN
    assert payload["exp"] > time.time()


def test_jwt_tampering_rejected():
    token = mint_token(org_id=uuid.uuid4(), role=Role.VIEWER)
    parts = token.split(".")

    # Tamper with the payload (change role to admin)
    import base64
    import json

    padding = (4 - len(parts[1]) % 4) % 4
    payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * padding))
    payload["role"] = Role.ADMIN
    tampered_payload = base64.urlsafe_b64encode(
        json.dumps(payload).encode()
    ).rstrip(b"=").decode()

    tampered_token = f"{parts[0]}.{tampered_payload}.{parts[2]}"
    with pytest.raises(InvalidTokenError):
        decode_jwt(tampered_token)


def test_jwt_expired_token_rejected():
    token = create_jwt(
        {"org_id": str(uuid.uuid4()), "role": Role.VIEWER},
        expires_delta=timedelta(seconds=-10),  # expired 10 seconds ago
    )
    with pytest.raises(TokenExpiredError):
        decode_jwt(token)


def test_role_hierarchy_permissions():
    assert role_has_access(Role.OWNER, Role.ADMIN) is True
    assert role_has_access(Role.ADMIN, Role.SOLUTIONS_ENGINEER) is True
    assert role_has_access(Role.SOLUTIONS_ENGINEER, Role.SALES) is True
    assert role_has_access(Role.SALES, Role.VIEWER) is True
    assert role_has_access(Role.VIEWER, Role.ADMIN) is False
    assert role_has_access(Role.SALES, Role.SOLUTIONS_ENGINEER) is False

    assert role_rank(Role.OWNER) > role_rank(Role.ADMIN)
    assert role_rank(Role.ADMIN) > role_rank(Role.SOLUTIONS_ENGINEER)


def test_auth_token_endpoint():
    target_org = str(uuid.uuid4())
    resp = client.post(
        "/auth/token",
        json={"org_id": target_org, "role": "solutions_engineer"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["org_id"] == target_org
    assert data["role"] == "solutions_engineer"

    # Verify the minted token is accepted by /auth/me
    token = data["access_token"]
    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["org_id"] == target_org
    assert me_data["role"] == "solutions_engineer"
    assert me_data["can_write_catalog"] is True
    assert me_data["is_owner"] is False


def test_auth_unauthenticated_request_rejected():
    prev_mode = settings.auth_mode
    try:
        settings.auth_mode = "jwt"
        resp = client.get("/auth/me")
        assert resp.status_code == 401
        assert "authentication required" in resp.json()["detail"].lower()
    finally:
        settings.auth_mode = prev_mode
