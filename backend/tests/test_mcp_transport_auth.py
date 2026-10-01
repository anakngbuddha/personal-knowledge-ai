"""HTTP-level authorization for the custom MCP server (audit findings 1, 2, 3, 15).

These go through the real routes (TestClient), token decoding, membership lookup and
the shared document predicate, instead of calling handlers with a mock principal.
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes import mcp_server as mcp_routes
from app.core.config import settings
from app.db.models import AccessGrant, Base, Document, Organization, Workspace
from app.db.session import get_db
from app.main import app
from app.security.accounts import OrganizationMembership, UserAccount
from app.security.jwt import decode_jwt, mint_token
from app.security.labels import ApprovalState, Role, Sensitivity
from app.security.principal import Principal

client = TestClient(app)
BASE = "/api/mcp/custom-server"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):  # noqa: ARG001
    return "JSON"


def _doc(org_id, ws_id, name, sensitivity):
    return Document(
        id=uuid.uuid4(),
        org_id=org_id,
        workspace_id=ws_id,
        filename=name,
        original_filename=name,
        file_type="pdf",
        storage_key=f"{org_id}/{name}",
        file_size=100,
        sensitivity=str(sensitivity),
        approval_state=str(ApprovalState.APPROVED),
        status="ready",
        is_current=True,
        is_demo=False,
    )


@pytest.fixture
def env():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(
        engine,
        tables=[
            Organization.__table__,
            Workspace.__table__,
            AccessGrant.__table__,
            Document.__table__,
            UserAccount.__table__,
            OrganizationMembership.__table__,
        ],
    )
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = Session()
    org_a = Organization(id=uuid.uuid4(), slug="mcp-a", name="A")
    org_b = Organization(id=uuid.uuid4(), slug="mcp-b", name="B")
    db.add_all([org_a, org_b])
    db.commit()
    ws_a = Workspace(id=uuid.uuid4(), org_id=org_a.id, name="WA")
    ws_b = Workspace(id=uuid.uuid4(), org_id=org_b.id, name="WB")
    db.add_all([ws_a, ws_b])
    db.commit()

    users = {}
    for key, role, active in (
        ("owner", Role.OWNER, True),
        ("viewer", Role.VIEWER, True),
        ("revoked", Role.SOLUTIONS_ENGINEER, False),
        ("downgraded", Role.VIEWER, True),
    ):
        account = UserAccount(id=uuid.uuid4(), email=f"{key}@example.com", display_name=key, password_hash="x")
        db.add(account)
        db.flush()
        db.add(OrganizationMembership(org_id=org_a.id, user_id=account.id, role=str(role), is_active=active))
        users[key] = account.id
    db.commit()

    internal = _doc(org_a.id, ws_a.id, "internal.pdf", Sensitivity.INTERNAL)
    secret = _doc(org_a.id, ws_a.id, "customer.pdf", Sensitivity.CUSTOMER_DATA)
    other_org = _doc(org_b.id, ws_b.id, "other.pdf", Sensitivity.INTERNAL)
    db.add_all([internal, secret, other_org])
    db.commit()

    def _get_db():
        inner = Session()
        try:
            yield inner
        finally:
            inner.close()

    app.dependency_overrides[get_db] = _get_db
    db.org_a, db.org_b = org_a.id, org_b.id
    db.users = users
    db.internal, db.secret, db.other = internal.id, secret.id, other_org.id
    try:
        yield db
    finally:
        app.dependency_overrides.pop(get_db, None)
        mcp_routes._SSE_SESSIONS.clear()
        db.close()


def _token(env, key, role=Role.VIEWER, org=None):
    return mint_token(org_id=org or env.org_a, user_id=env.users[key], role=str(role), extra_claims={"typ": "mcp", "scope": "mcp:read mcp:write"})


def _call(token, name, arguments):
    resp = client.post(
        f"{BASE}/rpc",
        headers={"Authorization": f"Bearer {token}"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}},
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()["result"]
    return result, json.loads(result["content"][0]["text"])


def test_message_without_token_is_rejected(env):
    resp = client.post(f"{BASE}/message", params={"sessionId": "nope"}, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert resp.status_code == 401


def test_message_without_token_on_authenticated_session_is_rejected(env):
    owner = Principal(org_id=env.org_a, user_id=env.users["owner"], role=Role.OWNER)
    sid = mcp_routes.register_mcp_session(owner)
    resp = client.post(f"{BASE}/message", params={"sessionId": sid}, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert resp.status_code == 401
    assert mcp_routes._SSE_SESSIONS[sid].queue.empty()


def test_message_to_unknown_session_gets_no_direct_reply(env):
    resp = client.post(
        f"{BASE}/message",
        params={"sessionId": "does-not-exist"},
        headers={"Authorization": f"Bearer {_token(env, 'owner', Role.OWNER)}"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    assert resp.status_code == 404
    assert "tools" not in resp.text


def test_message_from_another_user_cannot_use_the_session(env):
    owner = Principal(org_id=env.org_a, user_id=env.users["owner"], role=Role.OWNER)
    sid = mcp_routes.register_mcp_session(owner)
    resp = client.post(
        f"{BASE}/message",
        params={"sessionId": sid},
        headers={"Authorization": f"Bearer {_token(env, 'viewer')}"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    assert resp.status_code == 403
    assert mcp_routes._SSE_SESSIONS[sid].queue.empty()


def test_session_owner_message_is_delivered_over_sse(env):
    owner = Principal(org_id=env.org_a, user_id=env.users["owner"], role=Role.OWNER)
    sid = mcp_routes.register_mcp_session(owner)
    resp = client.post(
        f"{BASE}/message",
        params={"sessionId": sid},
        headers={"Authorization": f"Bearer {_token(env, 'owner', Role.OWNER)}"},
        json={"jsonrpc": "2.0", "id": 7, "method": "tools/list"},
    )
    assert resp.status_code == 202
    queued = mcp_routes._SSE_SESSIONS[sid].queue.get_nowait()
    assert queued["id"] == 7
    assert queued["result"]["tools"]


def test_rpc_requires_a_token(env):
    resp = client.post(f"{BASE}/rpc", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert resp.status_code == 401


def test_revoked_member_is_rejected_before_expiry(env):
    resp = client.post(
        f"{BASE}/rpc",
        headers={"Authorization": f"Bearer {_token(env, 'revoked', Role.SOLUTIONS_ENGINEER)}"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    assert resp.status_code == 403


def test_downgraded_member_role_claim_is_ignored(env):
    # Token still says admin; the membership says viewer. Membership wins.
    result, payload = _call(_token(env, "downgraded", Role.ADMIN), "create_note", {"title": "t", "body": "b"})
    assert result["isError"] is True
    assert "forbidden" in payload["error"]


def test_viewer_cannot_read_a_document_search_would_hide(env):
    result, payload = _call(_token(env, "viewer"), "read_document", {"document_id": str(env.secret)})
    assert result["isError"] is True
    assert "not found" in payload["error"]


def test_list_documents_applies_sensitivity_and_tenant(env):
    _, viewer = _call(_token(env, "viewer"), "list_documents", {})
    ids = {d["id"] for d in viewer["documents"]}
    assert str(env.internal) in ids
    assert str(env.secret) not in ids
    assert str(env.other) not in ids

    _, owner = _call(_token(env, "owner", Role.OWNER), "list_documents", {})
    ids = {d["id"] for d in owner["documents"]}
    assert {str(env.internal), str(env.secret)} <= ids
    assert str(env.other) not in ids


def test_wrong_organization_token_sees_nothing_from_org_a(env):
    _, payload = _call(_token(env, "viewer", org=env.org_b), "list_documents", {})
    ids = {d["id"] for d in payload["documents"]}
    assert str(env.internal) not in ids
    assert str(env.secret) not in ids


def test_minted_mcp_tokens_are_short_lived_and_scoped(env, monkeypatch):
    monkeypatch.setattr(settings, "mcp_token_max_minutes", 60)
    viewer = Principal(org_id=env.org_a, user_id=env.users["viewer"], role=Role.VIEWER)
    token = mcp_routes._mint_mcp_jwt(viewer, 60 * 24 * 30)
    claims = decode_jwt(token)
    assert claims["exp"] - claims["iat"] <= 60 * 60
    assert claims["scope"] == "mcp:read"
    assert claims["typ"] == "mcp"
