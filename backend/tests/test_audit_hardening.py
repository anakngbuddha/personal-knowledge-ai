"""Regression cases for the pasted security audit: attack inputs must fail closed."""
import asyncio
import logging
import time
import uuid
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.errors import AppError, StorageError, UnsafeFile
from app.main import app
from app.security.jwt import create_jwt, decode_jwt, InvalidTokenError, TokenExpiredError
from app.security.deps import resolve_principal, require_document_write, require_document_approval
from app.security.principal import Principal
from app.security.privacy import audit_details, redact_text
from app.storage.local import LocalStorage
from app.sso.transactions import SsoTransaction, begin, consume


@pytest.mark.parametrize("claims", [{"exp": 1000}, {"iat": 1031, "exp": 2000}, {"nbf": 1031, "exp": 2000}, {"exp": "2000"}, {"exp": float("nan")}, {"iat": 1000, "exp": 100000000}])
def test_invalid_jwt_times(claims, monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1000)
    with pytest.raises((InvalidTokenError, TokenExpiredError)):
        decode_jwt(create_jwt(claims))


def test_legacy_token_endpoint_never_mints(monkeypatch):
    monkeypatch.setattr(settings, "allow_legacy_token_endpoint", True)
    assert TestClient(app).post("/auth/token", json={"role": "owner"}).status_code == 410


@pytest.mark.parametrize("role", ["viewer", "sales"])
def test_low_roles_cannot_write_or_approve(role):
    principal = Principal(org_id=uuid.uuid4(), user_id=None, role=role)
    for guard in (require_document_write, require_document_approval):
        with pytest.raises(HTTPException) as exc:
            guard(principal)
        assert exc.value.status_code == 403


def test_mcp_requires_type_and_explicit_read_scope():
    from app.api.routes.mcp_server import resolve_mcp_principal
    for claims in ({"role": "owner"}, {"typ": "mcp", "scope": "mcp:write"}, {"typ": "mcp", "scope": []}):
        with pytest.raises(HTTPException) as exc:
            resolve_mcp_principal(None, create_jwt(claims))
        assert exc.value.status_code == 401


def test_mcp_rejects_query_token():
    assert TestClient(app).get("/api/mcp/custom-server/sse?token=secret").status_code == 400


@pytest.mark.parametrize("key", ["../outside", "a/../../outside", "/absolute", "C:\\outside"])
def test_storage_escape_is_rejected(tmp_path, monkeypatch, key):
    monkeypatch.setattr(settings, "local_storage_dir", str(tmp_path))
    with pytest.raises(StorageError):
        LocalStorage().put(key, b"data")
    assert not list(tmp_path.iterdir())


def test_upload_limit_at_service_boundary(monkeypatch):
    from app.documents.service import create_document
    monkeypatch.setattr(settings, "max_upload_mb", 0)
    with pytest.raises(AppError) as exc:
        create_document(None, principal=Principal(org_id=uuid.uuid4(), user_id=None), original_filename="a.txt", data=b"a")
    assert exc.value.status_code == 413


def test_rfp_limits(monkeypatch):
    from app.playbooks.rfp import parse_spreadsheet
    monkeypatch.setattr(settings, "catalog_import_max_rows", 1)
    with pytest.raises(AppError):
        parse_spreadsheet(b"requirement\none\ntwo\n", "r.csv")
    with pytest.raises(AppError):
        parse_spreadsheet(b"requirement\n" + b"a"*20001, "r.csv")


def test_job_must_match_document_tenant(monkeypatch):
    from app.jobs.worker import execute_claimed
    org = uuid.uuid4()
    document = SimpleNamespace(org_id=org, workspace_id=uuid.uuid4())
    db = SimpleNamespace(get=lambda model, key: document if model.__name__ == "Document" else SimpleNamespace(org_id=org))
    with pytest.raises(UnsafeFile):
        execute_claimed(db, SimpleNamespace(id=uuid.uuid4(), kind="ingest", document_id=uuid.uuid4(), org_id=uuid.uuid4()))


def test_audit_redacts_and_bounds_nested_secrets():
    details = audit_details({"token": "secret", "nested": {"password": "secret"}, "items": ["x"*10000]*1000})
    assert "secret" not in str(details)
    assert len(str(details)) < 10000
    assert "abc.def.ghi" not in redact_text("Authorization: Bearer abc.def.ghi")
    assert "hunter2" not in redact_text("postgresql://name:hunter2@db/app password=hunter2")


def test_sso_state_bound_expiring_and_one_time(monkeypatch):
    engine = create_engine("sqlite://")
    SsoTransaction.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as db:
        state, binding, row = begin(db, "oidc")
        with pytest.raises(InvalidTokenError):
            consume(db, state, "wrong-browser", "oidc")
        with pytest.raises(InvalidTokenError):
            consume(db, state, binding, "saml")
        assert consume(db, state, binding, "oidc").nonce == row.nonce
        with pytest.raises(InvalidTokenError):
            consume(db, state, binding, "oidc")
        state, binding, row = begin(db, "oidc")
        monkeypatch.setattr(time, "time", lambda: row.expires_at+1)
        with pytest.raises(InvalidTokenError):
            consume(db, state, binding, "oidc")


def test_credentials_reject_weak_keys_and_support_rotation(monkeypatch):
    from cryptography.fernet import Fernet
    from app.mcp.credentials import encrypt_secret, decrypt_secret, CredentialError
    monkeypatch.setattr(settings, "mcp_credentials_key", "weak-passphrase")
    with pytest.raises(CredentialError):
        encrypt_secret("secret")
    old_key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "mcp_credentials_key", old_key)
    monkeypatch.setattr(settings, "credentials_key_id", "old")
    blob = encrypt_secret("secret")
    assert blob.startswith(b"pka:old:")
    monkeypatch.setattr(settings, "mcp_credentials_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "credentials_key_id", "new")
    monkeypatch.setattr(settings, "credentials_previous_keys", {"old": old_key})
    assert decrypt_secret(blob) == "secret"
    monkeypatch.setattr(settings, "credentials_previous_keys", {})
    with pytest.raises(CredentialError):
        decrypt_secret(blob)


def test_security_headers_on_success_and_errors(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    for path in ("/", "/missing"):
        response = TestClient(app).get(path)
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert "max-age=" in response.headers["strict-transport-security"]
        assert len(response.headers["x-request-id"]) == 32


def test_mcp_coroutine_timeout_cancels():
    from app.mcp.client import _run_coro
    cancelled = []
    async def hung():
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.append(True)
    with pytest.raises(TimeoutError):
        _run_coro(hung(), timeout=0.01)
    assert cancelled == [True]


@pytest.mark.parametrize("target_role", ["admin", "owner"])
def test_admin_cannot_assign_peer_or_owner(target_role):
    from app.api.routes.auth import add_member, MemberCreate
    principal = Principal(org_id=uuid.uuid4(), user_id=uuid.uuid4(), role="admin")
    with pytest.raises(HTTPException) as exc:
        add_member(MemberCreate(email="fixture@example.test", password="testpassword123", display_name="Fixture", role=target_role), principal, None)
    assert exc.value.status_code == 403


def test_admin_cannot_demote_owner_and_last_owner_is_preserved(monkeypatch):
    from app.api.routes.auth import update_member_role, RoleUpdate
    from app.db.models import Organization
    from app.security.accounts import OrganizationMembership, UserAccount
    engine = create_engine("sqlite://")
    for table in (Organization.__table__, UserAccount.__table__, OrganizationMembership.__table__):
        table.create(engine)
    with Session(engine) as db:
        org = Organization(id=uuid.uuid4(), slug="rbac-test", name="Test")
        user = UserAccount(id=uuid.uuid4(), email="owner@example.test", display_name="Owner", password_hash="unused")
        db.add_all([org, user]); db.flush()
        member = OrganizationMembership(org_id=org.id, user_id=user.id, role="owner")
        db.add(member); db.commit()
        admin = Principal(org_id=org.id, user_id=uuid.uuid4(), role="admin")
        with pytest.raises(HTTPException) as exc:
            update_member_role(user.id, RoleUpdate(role="viewer"), admin, db)
        assert exc.value.status_code == 403
        owner = Principal(org_id=org.id, user_id=user.id, role="owner")
        with pytest.raises(HTTPException) as exc:
            update_member_role(user.id, RoleUpdate(role="viewer"), owner, db)
        assert exc.value.status_code == 409
        assert member.role == "owner"


def test_non_admin_cannot_approve_at_creation():
    from app.documents.service import create_document
    from app.documents.metadata import DocumentMetadataIn
    principal = Principal(org_id=uuid.uuid4(), user_id=None, role="solutions_engineer")
    with pytest.raises(AppError) as exc:
        create_document(None, principal=principal, original_filename="a.txt", data=b"text", metadata=DocumentMetadataIn(approval_state="approved"))
    assert exc.value.status_code == 403


def test_declared_request_budget_rejected_before_body(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    response = TestClient(app).post("/documents", content=b"a", headers={"Content-Length": "999999999"})
    assert response.status_code == 413
    assert response.headers["x-content-type-options"] == "nosniff"


def test_isolated_parser_success_and_hard_deadline():
    from app.documents.isolated import extract_isolated
    from app.documents.limits import ParseLimits
    from app.core.errors import ExtractionTimeout
    result = extract_isolated(b"A parser fixture", "txt", ParseLimits(timeout_seconds=15))
    assert "A parser fixture" in " ".join(block.text for block in result.blocks)
    with pytest.raises(ExtractionTimeout):
        extract_isolated(b"A parser fixture", "txt", ParseLimits(timeout_seconds=0.00001))


def test_sso_verified_email_uses_local_role_and_denies_other_tenant():
    from app.sso.service import issue_local_token
    from app.db.models import Organization
    from app.security.accounts import UserAccount, OrganizationMembership
    engine = create_engine("sqlite://")
    for table in (Organization.__table__, UserAccount.__table__, OrganizationMembership.__table__):
        table.create(engine)
    with Session(engine) as db:
        org = Organization(id=uuid.uuid4(), slug="sso-test", name="Test")
        user = UserAccount(id=uuid.uuid4(), email="fixture@example.test", display_name="Fixture", password_hash="unused")
        db.add_all([org, user]); db.flush()
        db.add(OrganizationMembership(org_id=org.id, user_id=user.id, role="viewer")); db.commit()
        result = issue_local_token(db=db, org_id=org.id, subject="provider-subject", role="owner", verified_email=user.email)
        assert decode_jwt(result["access_token"])["role"] == "viewer"
        with pytest.raises(AppError):
            issue_local_token(db=db, org_id=uuid.uuid4(), subject="provider-subject", role="owner", verified_email=user.email)


def test_upload_quota_checked_before_scanner_or_storage():
    from app.documents.service import create_document
    counts = iter([uuid.uuid4(), 100, 0])
    db = SimpleNamespace(scalar=lambda statement: next(counts))
    with pytest.raises(AppError) as exc:
        create_document(db, principal=Principal(org_id=uuid.uuid4(), user_id=None, role="owner"), original_filename="a.txt", data=b"text")
    assert exc.value.status_code == 429


def test_identity_lookup_restores_default_deny_after_error():
    from app.db.session import verified_identity_lookup
    with Session(create_engine("sqlite://")) as db:
        db.info["org_id"] = "original"
        with pytest.raises(RuntimeError):
            with verified_identity_lookup(db):
                assert db.info["rls_bypass"] is True
                assert "org_id" not in db.info
                raise RuntimeError("fixture")
        assert db.info == {"org_id": "original"}


def test_production_mcp_child_requires_os_sandbox(monkeypatch):
    from app.mcp.client import _stdio_transport
    from app.mcp.servers import ServerSpec
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "mcp_child_sandbox_command", "")
    with pytest.raises(AppError) as exc:
        _stdio_transport(ServerSpec(slug="brave", org_id=str(uuid.uuid4())))
    assert exc.value.status_code == 503


def test_signed_urls_redacted_from_logs():
    assert "private.example" not in redact_text("download https://private.example/customer.pdf?signature=secret")


def test_headers_and_stable_error_on_unhandled_failure():
    from app.security.headers import SecurityMiddleware
    async def broken(scope, receive, send):
        raise RuntimeError("fixture failure")
    response = TestClient(SecurityMiddleware(broken)).get("/")
    assert response.status_code == 500
    assert response.json() == {"detail": "request failed"}
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("cursor", ["not-base64!", "e30", "W10", "x"*513])
def test_bad_page_cursor_is_rejected(cursor):
    from app.db.pagination import seek_before
    from app.db.models import Document
    with pytest.raises(AppError) as exc:
        seek_before(select(Document), Document.uploaded_at, Document.id, cursor)
    assert exc.value.status_code == 422


def test_oidc_code_exchange_verifies_signature_nonce_and_pkce(monkeypatch):
    from app.sso import standards
    from joserfc import jwt
    from joserfc.jwk import RSAKey
    import httpx
    key = RSAKey.generate_key(2048)
    now = int(time.time())
    claims = {"iss": "https://idp.example", "aud": "test-client", "sub": "subject", "iat": now, "exp": now+300, "nonce": "bound-nonce", "email": "fixture@example.test", "email_verified": True}
    tokens = {"id_token": jwt.encode({"alg": "RS256"}, claims, key)}
    monkeypatch.setattr(settings, "oidc_issuer", "https://idp.example")
    monkeypatch.setattr(settings, "oidc_client_id", "test-client")
    monkeypatch.setattr(settings, "oidc_audience", "test-client")
    monkeypatch.setattr(standards, "_metadata", lambda: {"token_endpoint": "https://idp.example/token", "jwks_uri": "https://idp.example/keys"})
    calls = []
    class OAuth:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def fetch_token(self, url, **kwargs):
            calls.append(kwargs)
            return tokens
    class Keys(OAuth):
        def get(self, url):
            return httpx.Response(200, json={"keys": [key.as_dict(private=False)]}, request=httpx.Request("GET", url))
    monkeypatch.setattr(standards, "OAuth2Client", OAuth)
    monkeypatch.setattr(standards.httpx, "Client", Keys)
    monkeypatch.setattr(standards, "issue_local_token", lambda **kwargs: kwargs)
    result = standards.oidc_exchange(None, "code", "bound-nonce", "pkce-verifier", uuid.uuid4())
    assert result["verified_email"] == "fixture@example.test"
    assert calls[0]["code_verifier"] == "pkce-verifier"
    with pytest.raises(Exception, match="nonce"):
        standards.oidc_exchange(None, "code", "wrong-nonce", "pkce-verifier", uuid.uuid4())
    tokens["id_token"] = jwt.encode({"alg": "RS256"}, claims, RSAKey.generate_key(2048))
    with pytest.raises(Exception, match="signature"):
        standards.oidc_exchange(None, "code", "bound-nonce", "pkce-verifier", uuid.uuid4())
