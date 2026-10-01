"""Phase 10: tribal notes, vendor freshness, SSO, and restore drills."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.models import (
    AccessGrant,
    AuditLog,
    Base,
    FreshnessAlert,
    FreshnessStatus,
    Note,
    NoteLink,
    Organization,
    Product,
    RestoreDrill,
    SsoProvider,
    VendorSource,
    Workspace,
)
from app.db.session import get_db
from app.freshness.scraper import FetchSnapshot, check_source, create_source
from app.main import app
from app.notes.wikilinks import extract_wikilinks
from app.ops.restore import dump_tenant, run_restore_drill
from app.security.jwt import decode_jwt, mint_token
from app.security.labels import Role
from app.sso.oidc import mint_oidc_id_token
from app.sso.saml import sign_saml_assertion

client = TestClient(app)


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):  # noqa: ARG001
    return "JSON"


def _engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _tables():
    return [
        Organization.__table__,
        AccessGrant.__table__,
        Workspace.__table__,
        Product.__table__,
        Note.__table__,
        NoteLink.__table__,
        VendorSource.__table__,
        FreshnessAlert.__table__,
        RestoreDrill.__table__,
        SsoProvider.__table__,
        AuditLog.__table__,
    ]


@pytest.fixture
def phase10_db(monkeypatch):
    monkeypatch.setattr(settings, "freshness_worker_enabled", False)
    monkeypatch.setattr(settings, "sso_enabled", True)
    monkeypatch.setattr(settings, "oidc_issuer", "https://idp.example")
    monkeypatch.setattr(settings, "oidc_client_id", "se-workspace")
    monkeypatch.setattr(settings, "oidc_audience", "se-workspace")
    monkeypatch.setattr(settings, "oidc_client_secret", "oidc-test-secret")
    monkeypatch.setattr(settings, "saml_idp_issuer", "https://idp.example/saml")
    monkeypatch.setattr(settings, "saml_entity_id", "http://localhost:8000/auth/saml/acs")
    monkeypatch.setattr(settings, "saml_idp_secret", "saml-test-secret")
    monkeypatch.setattr(settings, "saml_allow_unsigned", False)
    monkeypatch.setattr(settings, "restore_drill_sla_seconds", 30.0)

    engine = _engine()
    Base.metadata.create_all(engine, tables=_tables())
    SessionClass = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = SessionClass()
    org_a = Organization(id=uuid.uuid4(), slug="org-a", name="A")
    org_b = Organization(id=uuid.uuid4(), slug="org-b", name="B")
    db.add_all([org_a, org_b])
    db.flush()
    ws_a = Workspace(id=uuid.uuid4(), org_id=org_a.id, name="A workspace")
    ws_b = Workspace(id=uuid.uuid4(), org_id=org_b.id, name="B workspace")
    db.add_all([ws_a, ws_b])
    db.commit()

    def _get_db():
        inner = SessionClass()
        try:
            yield inner
        finally:
            inner.close()

    app.dependency_overrides[get_db] = _get_db
    db.org_a_id = org_a.id
    db.org_b_id = org_b.id
    db.ws_a_id = ws_a.id
    db.ws_b_id = ws_b.id
    db.SessionClass = SessionClass
    try:
        yield db
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()


def _auth(org_id: uuid.UUID, role: str = Role.SOLUTIONS_ENGINEER, user_id: uuid.UUID | None = None) -> dict:
    token = mint_token(org_id=org_id, user_id=user_id or uuid.uuid4(), role=role)
    return {"Authorization": f"Bearer {token}"}


def test_wikilink_parser_extracts_kinds_and_aliases():
    links = extract_wikilinks(
        "See [[product:Firewall Plus|Firewall]] and [[account:Acme Corp]] plus [[note:sizing-acme]]."
    )
    by_kind = {item.kind: item for item in links}
    assert by_kind["product"].target_ref == "firewall-plus"
    assert by_kind["product"].display_text == "Firewall"
    assert by_kind["account"].target_ref == "acme-corp"
    assert by_kind["note"].target_ref == "sizing-acme"


def test_note_wikilinks_resolve_products_and_accounts(phase10_db):
    db = phase10_db
    product = Product(
        org_id=db.org_a_id,
        workspace_id=db.ws_a_id,
        name="Firewall Plus",
        slug="firewall-plus",
        vendor="Own",
        category="Network",
    )
    db.add(product)
    db.commit()

    headers = _auth(db.org_a_id)
    created = client.post(
        "/notes",
        headers=headers,
        json={
            "title": "Acme sizing",
            "body": "Deploy [[product:firewall-plus]] at [[account:acme-corp]].",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    kinds = {link["target_kind"]: link for link in body["links"]}
    assert kinds["product"]["resolved"] is True
    assert kinds["product"]["resolved_id"] == str(product.id)
    assert kinds["account"]["resolved"] is True
    assert kinds["account"]["target_ref"] == "acme-corp"

    listed = client.get("/notes", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    back = client.get("/notes/by-link/account/acme-corp", headers=headers)
    assert back.status_code == 200
    assert back.json()["total"] == 1


def test_notes_are_tenant_isolated(phase10_db):
    db = phase10_db
    created = client.post(
        "/notes",
        headers=_auth(db.org_a_id),
        json={"title": "Secret playbook", "body": "internal only"},
    )
    note_id = created.json()["id"]
    other = client.get(f"/notes/{note_id}", headers=_auth(db.org_b_id))
    assert other.status_code == 404


def test_freshness_change_raises_staleness_alert(phase10_db):
    db = phase10_db
    source = create_source(
        db,
        org_id=db.org_a_id,
        workspace_id=db.ws_a_id,
        label="Vendor datasheet",
        url="https://vendor.example/datasheet.pdf",
    )
    payloads = {"https://vendor.example/datasheet.pdf": b"datasheet-v1"}

    def fetcher(url: str) -> FetchSnapshot:
        return FetchSnapshot(data=payloads[url])

    first = check_source(db, source, fetcher=fetcher)
    assert first.status == FreshnessStatus.FRESH
    assert first.changed is False
    assert first.alert_id is None

    payloads["https://vendor.example/datasheet.pdf"] = b"datasheet-v2"
    db.refresh(source)
    second = check_source(db, source, fetcher=fetcher)
    assert second.changed is True
    assert second.status == FreshnessStatus.STALE
    assert second.alert_id is not None

    headers = _auth(db.org_a_id)
    alerts = client.get("/freshness/alerts", headers=headers)
    assert alerts.status_code == 200
    assert alerts.json()["total"] == 1
    alert_id = alerts.json()["alerts"][0]["id"]
    acked = client.post(f"/freshness/alerts/{alert_id}/ack", headers=headers)
    assert acked.status_code == 200
    assert acked.json()["acknowledged_at"] is not None


def test_freshness_sources_are_tenant_isolated(phase10_db):
    db = phase10_db
    created = client.post(
        "/freshness/sources",
        headers=_auth(db.org_a_id),
        json={"label": "A sheet", "url": "https://a.example/doc.pdf"},
    )
    assert created.status_code == 201, created.text
    source_id = created.json()["id"]
    other = client.post(f"/freshness/sources/{source_id}/check", headers=_auth(db.org_b_id))
    assert other.status_code == 404


def test_oidc_implicit_callback_is_disabled(phase10_db):
    response = client.post("/auth/oidc/callback", json={"id_token": "arbitrary", "nonce": "n-1"})
    assert response.status_code == 410


def test_oidc_rejects_wrong_issuer(phase10_db):
    id_token = mint_oidc_id_token(
        issuer="https://evil.example",
        audience="se-workspace",
        subject=str(uuid.uuid4()),
        secret="oidc-test-secret",
        role=Role.VIEWER,
    )
    response = client.post("/auth/oidc/callback", json={"id_token": id_token})
    assert response.status_code == 410


def test_saml_legacy_hmac_request_rejected(phase10_db):
    response = client.post("/auth/saml/acs", json={"SAMLResponse": "<Assertion/>", "signature": "hmac"})
    assert response.status_code == 422


def test_saml_expired_assertion_rejected(phase10_db):
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    xml = (
        "<Assertion>"
        "<Issuer>https://idp.example/saml</Issuer>"
        f"<Subject><NameID>{uuid.uuid4()}</NameID></Subject>"
        f'<Conditions NotOnOrAfter="{past}"/>'
        "</Assertion>"
    )
    signature = sign_saml_assertion(xml, "saml-test-secret")
    response = client.post("/auth/saml/acs", json={"SAMLResponse": xml, "signature": signature})
    assert response.status_code == 422


def test_restore_drill_round_trip_within_sla(phase10_db):
    db = phase10_db
    headers = _auth(db.org_a_id, role=Role.ADMIN)
    client.post(
        "/notes",
        headers=_auth(db.org_a_id),
        json={"title": "Drill note", "body": "[[account:acme]]"},
    )
    response = client.post("/ops/restore-drills", headers=headers, json={"sla_seconds": 30})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["within_sla"] is True
    assert body["row_counts_after"]["notes"] == 1
    snapshot = dump_tenant(db, db.org_a_id)
    assert snapshot["counts"]["notes"] == 1


def test_restore_drill_requires_admin(phase10_db):
    db = phase10_db
    response = client.post("/ops/restore-drills", headers=_auth(db.org_a_id, role=Role.SALES))
    assert response.status_code == 403


def test_restore_drill_service_records_failure_outside_sla(phase10_db, monkeypatch):
    db = phase10_db
    monkeypatch.setattr(settings, "restore_drill_sla_seconds", 0.0)
    note = Note(
        org_id=db.org_a_id,
        workspace_id=db.ws_a_id,
        title="Keep",
        slug="keep",
        body="body",
    )
    db.add(note)
    db.commit()
    drill = run_restore_drill(db, org_id=db.org_a_id, triggered_by=None, sla_seconds=-1.0)
    assert drill.status == "failed"
    assert drill.within_sla is False
    assert drill.error_message
