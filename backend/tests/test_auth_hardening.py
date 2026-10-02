"""Regression tests for the brute-force / OWASP audit (auth throttling, secrets,
enumeration, token audiences, health exposure, body limits, MCP client config)."""

from __future__ import annotations

import json
import secrets
import string
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, jwt_secret_problem, settings
from app.db.models import AccessGrant, Base, Organization
from app.db.session import get_db
from app.main import app
from app.security import auth_throttle
from app.security.accounts import (
    OrganizationMembership,
    UserAccount,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.security.jwt import mint_token
from app.security.passwords import password_problem
from app.security.principal import Principal

STRONG_SECRET = string.ascii_letters[:40]
client = TestClient(app)


@pytest.fixture(autouse=True)
def _fresh_counters():
    auth_throttle.reset_all()
    yield
    auth_throttle.reset_all()


@pytest.fixture
def auth_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[
        Organization.__table__, AccessGrant.__table__, UserAccount.__table__, OrganizationMembership.__table__,
    ])
    SessionClass = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = SessionClass()
    session.add(Organization(slug=settings.default_org_slug, name=settings.default_org_name))
    session.commit()

    def _get_test_db():
        inner = SessionClass()
        try:
            yield inner
        finally:
            inner.close()

    app.dependency_overrides[get_db] = _get_test_db
    try:
        yield session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


# --- JWT secret ---------------------------------------------------------------

@pytest.mark.parametrize("value", [
    "replace-with-a-random-32-plus-character-secret", "changeme", "short", "x" * 64, "ab" * 32,
])
def test_weak_jwt_secrets_are_flagged(value):
    assert jwt_secret_problem(value) is not None


def test_random_jwt_secrets_pass():
    assert jwt_secret_problem(secrets.token_urlsafe(48)) is None
    assert jwt_secret_problem(secrets.token_hex(32)) is None


def test_published_placeholder_refused_in_every_environment():
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings.model_validate({"environment": "development", "jwt_secret_key": "replace-with-a-random-32-plus-character-secret"})


def test_production_refuses_empty_or_low_entropy_secret():
    for value in ("", "x" * 40):
        with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
            Settings.model_validate({"environment": "production", "auth_mode": "jwt", "jwt_secret_key": value})


def test_empty_secret_outside_production_fails_closed():
    first = Settings.model_validate({"environment": "development", "jwt_secret_key": ""})
    second = Settings.model_validate({"environment": "development", "jwt_secret_key": ""})
    assert len(first.jwt_secret_key) >= 32
    assert first.jwt_secret_key != second.jwt_secret_key


def test_docs_are_off_in_production_by_default():
    assert Settings.model_validate({"environment": "development"}).docs_enabled is True
    prod = Settings.model_construct(environment="production", api_docs_enabled=None)
    assert prod.docs_enabled is False


# --- passwords ----------------------------------------------------------------

def test_password_hash_uses_current_work_factor_and_upgrades_old_hashes(monkeypatch):
    monkeypatch.setattr(settings, "password_pbkdf2_iterations", 120_000)
    encoded = hash_password("correct horse battery")
    assert encoded.split("$")[1] == "120000"
    assert verify_password("correct horse battery", encoded)
    assert not needs_rehash(encoded)
    monkeypatch.setattr(settings, "password_pbkdf2_iterations", 600_000)
    assert needs_rehash(encoded)


def test_tampered_round_count_is_not_computed():
    assert verify_password("anything-here", "pbkdf2_sha256$999999999$00$00") is False


@pytest.mark.parametrize("password", ["password123", "1234567890", "qwertyuiop", "aaaaaaaaaaaa"])
def test_common_passwords_rejected(password):
    assert password_problem(password) is not None


def test_email_based_password_rejected_and_passphrase_accepted():
    assert password_problem("johnsmith12", "johnsmith@example.test") is not None
    assert password_problem("violet-anchor-tundra-42", "johnsmith@example.test") is None


# --- throttling ---------------------------------------------------------------

def test_sliding_window_counts_and_expires():
    counter = auth_throttle.SlidingWindowCounter(max_keys=3)
    assert [counter.add("k", 60, now=t) for t in (0, 1, 2)] == [1, 2, 3]
    assert counter.count("k", 60, now=60.5) == 2
    assert counter.count("k", 60, now=200) == 0
    for i in range(10):
        counter.add(f"other-{i}", 60, now=300)
    assert len(counter._events) <= 3


def test_enforce_raises_429_with_retry_after(monkeypatch):
    monkeypatch.setattr(settings, "auth_rate_limit_enabled", True)
    auth_throttle.enforce("t", "ip", 2, 60)
    auth_throttle.enforce("t", "ip", 2, 60)
    with pytest.raises(HTTPException) as exc:
        auth_throttle.enforce("t", "ip", 2, 60)
    assert exc.value.status_code == 429
    assert int(exc.value.headers["Retry-After"]) >= 1


def test_client_ip_only_trusts_configured_proxy_hops(monkeypatch):
    request = SimpleNamespace(headers={"x-forwarded-for": "6.6.6.6, 203.0.113.9"}, client=SimpleNamespace(host="10.0.0.1"))
    monkeypatch.setattr(settings, "trusted_proxy_hops", 0)
    assert auth_throttle.client_ip(request) == "10.0.0.1"
    monkeypatch.setattr(settings, "trusted_proxy_hops", 1)
    assert auth_throttle.client_ip(request) == "203.0.113.9"


def test_login_is_throttled_per_account(auth_db, monkeypatch):
    monkeypatch.setattr(settings, "auth_rate_limit_enabled", True)
    monkeypatch.setattr(settings, "auth_login_ip_per_minute", 1000)
    monkeypatch.setattr(settings, "auth_login_failures_per_account", 3)
    auth_db.add(UserAccount(email="victim@example.test", display_name="V", password_hash=hash_password("the-real-passphrase")))
    auth_db.commit()
    body = {"email": "victim@example.test", "password": "wrong-guess-123"}
    assert [client.post("/auth/login", json=body).status_code for _ in range(3)] == [401, 401, 401]
    blocked = client.post("/auth/login", json=body)
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_login_is_throttled_per_ip(auth_db, monkeypatch):
    monkeypatch.setattr(settings, "auth_rate_limit_enabled", True)
    monkeypatch.setattr(settings, "auth_login_ip_per_minute", 2)
    codes = [client.post("/auth/login", json={"email": f"u{i}@example.test", "password": "whatever-123"}).status_code for i in range(3)]
    assert codes == [401, 401, 429]


def test_failed_login_is_logged_without_the_email(auth_db, caplog):
    import logging
    with caplog.at_level(logging.INFO, logger="app.security.events"):
        client.post("/auth/login", json={"email": "nobody@example.test", "password": "whatever-123"})
    text = caplog.text
    assert "login_failed" in text
    assert "nobody@example.test" not in text


def test_signup_can_be_disabled(auth_db, monkeypatch):
    monkeypatch.setattr(settings, "signup_enabled", False)
    resp = client.post("/auth/signup", json={"email": "a@example.test", "password": "violet-anchor-tundra-42",
                                             "display_name": "A", "organization_name": "A Org"})
    assert resp.status_code == 403


def test_signup_conflict_does_not_confirm_the_email(auth_db):
    auth_db.add(UserAccount(email="taken@example.test", display_name="T", password_hash=hash_password("the-real-passphrase")))
    auth_db.commit()
    taken = client.post("/auth/signup", json={"email": "taken@example.test", "password": "violet-anchor-tundra-42",
                                              "display_name": "X", "organization_name": "Brand New Org"})
    org_clash = client.post("/auth/signup", json={"email": "fresh@example.test", "password": "violet-anchor-tundra-42",
                                                  "display_name": "X", "organization_name": settings.default_org_slug})
    assert taken.status_code == org_clash.status_code == 409
    assert taken.json()["detail"] == org_clash.json()["detail"]
    assert "email" not in taken.json()["detail"].split(";")[0]


# --- token audiences and exposure ---------------------------------------------

def test_mcp_tokens_are_refused_by_the_web_api(auth_db, monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "jwt")
    token = mint_token(org_id=uuid.uuid4(), user_id=uuid.uuid4(), role="owner", extra_claims={"typ": "mcp", "scope": "mcp:read"})
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert "MCP" in resp.json()["detail"]


def test_dependency_health_requires_authentication(auth_db, monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "jwt")
    assert client.get("/health/dependencies").status_code == 401
    assert client.get("/health").status_code == 200


def test_dependency_health_requires_admin():
    from app.security.deps import require_admin
    with pytest.raises(HTTPException) as exc:
        require_admin(Principal(org_id=uuid.uuid4(), user_id=uuid.uuid4(), role="viewer"))
    assert exc.value.status_code == 403


def test_json_bodies_get_a_small_budget(monkeypatch):
    from app.security.headers import body_budget
    monkeypatch.setattr(settings, "max_json_body_mb", 1)
    monkeypatch.setattr(settings, "max_upload_mb", 25)
    assert body_budget({b"content-type": b"application/json"}) == 1024 * 1024
    assert body_budget({b"content-type": b"multipart/form-data; boundary=x"}) > 25 * 1024 * 1024
    resp = client.post("/auth/login", content=b"{}", headers={"Content-Type": "application/json", "Content-Length": str(2 * 1024 * 1024)})
    assert resp.status_code == 413


# --- members ------------------------------------------------------------------

def test_add_member_refuses_existing_account_and_leaks_nothing(monkeypatch):
    from app.api.routes.auth import MemberCreate, add_member
    monkeypatch.setattr(settings, "members_attach_existing_accounts", False)
    engine = create_engine("sqlite://")
    for table in (Organization.__table__, UserAccount.__table__, OrganizationMembership.__table__):
        table.create(engine)
    with Session(engine) as db:
        org = Organization(id=uuid.uuid4(), slug="members-test", name="Test")
        other = UserAccount(id=uuid.uuid4(), email="someone@example.test", display_name="Other Tenant Name", password_hash="unused")
        db.add_all([org, other]); db.commit()
        owner = Principal(org_id=org.id, user_id=uuid.uuid4(), role="owner")
        with pytest.raises(HTTPException) as exc:
            add_member(MemberCreate(email="someone@example.test", display_name="Invitee", password="violet-anchor-tundra-42"), owner, db)
        assert exc.value.status_code == 409
        assert "Other Tenant Name" not in str(exc.value.detail)
        assert db.scalar(select(OrganizationMembership).where(OrganizationMembership.user_id == other.id)) is None


# --- MCP client config --------------------------------------------------------

def test_generated_mcp_config_is_pinned():
    from app.api.routes import mcp_server
    request = SimpleNamespace(base_url="http://localhost:8000/")
    principal = Principal(org_id=uuid.uuid4(), user_id=uuid.uuid4(), role="owner")
    out = mcp_server.get_custom_mcp_config(request, principal)
    dumped = json.dumps(out.model_dump())
    assert "@latest" not in dumped
    assert f"mcp-remote@{settings.mcp_remote_npm_version}" in dumped
    if out.script_sha256:
        bootstrap = out.remote_python_config["mcpServers"][mcp_server.SERVER_NAME]["args"][1]
        assert out.script_sha256 in bootstrap
        assert "sys.exit" in bootstrap


def test_python_bootstrap_refuses_tampered_script(monkeypatch):
    import hashlib
    import urllib.request
    from app.api.routes.mcp_server import python_bootstrap
    good = b"RESULT = 'ran'\n"
    evil = b"RESULT = 'evil'\n"

    class Fake:
        def __init__(self, data): self.data = data
        def read(self): return self.data

    code = python_bootstrap("https://api.example.test/script", hashlib.sha256(good).hexdigest())
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: Fake(evil))
    with pytest.raises(SystemExit):
        exec(code, {})
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: Fake(good))
    scope: dict = {}
    exec(code, scope)
    assert scope["RESULT"] == "ran"
