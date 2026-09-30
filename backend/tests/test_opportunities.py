"""Opportunity coverage and tenant/owner boundaries."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import (
    AuditLog,
    Base,
    Document,
    Opportunity,
    OpportunityParticipant,
    OpportunityRequirement,
    Organization,
    Product,
    ProviderSkuMap,
    StoredPriceObservation,
    CommercialPolicyRecord,
    SalesQuote,
    SalesQuoteExport,
    SalesQuoteVersion,
    McpIntegration,
    SalesAccount,
    SalesClaim,
    Workspace,
)
from app.db.session import get_db
from app.main import app
from app.security.deps import resolve_principal
from app.security.accounts import OrganizationMembership, UserAccount
from app.security.labels import Role
from app.security.principal import Principal


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(element, compiler, **kw):
    return "JSON"


@pytest.fixture
def sales_api():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Organization.__table__,
            UserAccount.__table__,
            OrganizationMembership.__table__,
            Workspace.__table__,
            Document.__table__,
            Product.__table__,
            SalesAccount.__table__,
            SalesClaim.__table__,
            Opportunity.__table__,
            OpportunityParticipant.__table__,
            OpportunityRequirement.__table__,
            ProviderSkuMap.__table__,
            StoredPriceObservation.__table__,
            CommercialPolicyRecord.__table__,
            SalesQuote.__table__,
            SalesQuoteVersion.__table__,
            SalesQuoteExport.__table__,
            McpIntegration.__table__,
            AuditLog.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with session_factory() as db:
        org_a = Organization(slug="sales-a", name="Sales A")
        org_b = Organization(slug="sales-b", name="Sales B")
        db.add_all([org_a, org_b])
        db.commit()
        db.refresh(org_a)
        db.refresh(org_b)
        ids = (org_a.id, org_b.id)
        member_a = UserAccount(email="member-a@example.com", display_name="Member A", password_hash="test")
        member_b = UserAccount(email="member-b@example.com", display_name="Member B", password_hash="test")
        db.add_all([member_a, member_b])
        db.flush()
        db.add_all([
            OrganizationMembership(org_id=org_a.id, user_id=member_a.id, role=Role.SALES),
            OrganizationMembership(org_id=org_b.id, user_id=member_b.id, role=Role.SALES),
        ])
        db.commit()
        member_ids = (member_a.id, member_b.id)

    current = {
        "principal": Principal(org_id=ids[0], user_id=uuid.uuid4(), role=Role.SALES),
        "member_ids": member_ids,
        "session_factory": session_factory,
    }

    def _db():
        with session_factory() as db:
            yield db

    def _principal():
        return current["principal"]

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[resolve_principal] = _principal
    try:
        yield TestClient(app), current, ids
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(resolve_principal, None)
        engine.dispose()


def test_opportunity_requirement_review_and_conflict(sales_api):
    client, _, _ = sales_api
    account = client.post("/api/accounts", json={"name": "Example Customer"})
    assert account.status_code == 201
    opportunity = client.post(
        "/api/opportunities",
        json={"title": "Cloud migration", "account_id": account.json()["id"]},
    )
    assert opportunity.status_code == 201
    opportunity_id = opportunity.json()["id"]
    assert client.get("/api/opportunities").json()["items"][0]["id"] == opportunity_id

    requirement = client.post(
        f"/api/opportunities/{opportunity_id}/requirements",
        json={"original_text": "Backup must run daily", "priority": "must"},
    )
    assert requirement.status_code == 201
    requirement_id = requirement.json()["id"]
    coverage_url = f"/api/opportunities/{opportunity_id}/coverage"
    assert client.get(coverage_url).json()["ready_for_quote"] is False

    patch_url = f"/api/opportunities/{opportunity_id}/requirements/{requirement_id}"
    reviewed = client.patch(
        patch_url,
        json={"version": 1, "coverage_state": "covered", "coverage_note": "Backup SKU reviewed"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["version"] == 2
    assert client.get(coverage_url).json()["ready_for_quote"] is True
    assert client.patch(
        patch_url,
        json={"version": 1, "coverage_state": "gap", "coverage_note": "Stale edit"},
    ).status_code == 409


def test_opportunity_is_hidden_from_other_tenant_and_owner(sales_api):
    client, current, (org_a, org_b) = sales_api
    created = client.post("/api/opportunities", json={"title": "Private deal"})
    assert created.status_code == 201
    opportunity_id = created.json()["id"]

    current["principal"] = Principal(org_id=org_b, user_id=uuid.uuid4(), role=Role.ADMIN)
    assert client.get(f"/api/opportunities/{opportunity_id}").status_code == 404
    assert client.get("/api/opportunities").json()["items"] == []
    assert client.post(
        "/api/opportunities", json={"title": "Wrong account", "account_id": str(uuid.uuid4())}
    ).status_code == 404

    current["principal"] = Principal(org_id=org_a, user_id=uuid.uuid4(), role=Role.SALES)
    assert client.get(f"/api/opportunities/{opportunity_id}").status_code == 404
    assert client.post(
        f"/api/opportunities/{opportunity_id}/requirements",
        json={"original_text": "Should be denied"},
    ).status_code == 404
    current["principal"] = Principal(org_id=org_a, user_id=uuid.uuid4(), role=Role.VIEWER)
    assert client.post("/api/opportunities", json={"title": "Denied"}).status_code == 403


def test_review_requires_note_and_rejects_extra_fields(sales_api):
    client, _, _ = sales_api
    opportunity_id = client.post("/api/opportunities", json={"title": "Coverage"}).json()["id"]
    requirement_id = client.post(
        f"/api/opportunities/{opportunity_id}/requirements",
        json={"original_text": "4 vCPU"},
    ).json()["id"]
    url = f"/api/opportunities/{opportunity_id}/requirements/{requirement_id}"
    assert client.patch(url, json={"version": 1, "coverage_state": "covered"}).status_code == 422
    assert client.post(
        "/api/opportunities", json={"title": "Invalid", "org_id": str(uuid.uuid4())}
    ).status_code == 422


def test_participant_access_and_cross_tenant_grant(sales_api):
    client, current, (org_a, _) = sales_api
    opportunity_id = client.post("/api/opportunities", json={"title": "Shared deal"}).json()["id"]
    member_a, member_b = current["member_ids"]
    url = f"/api/opportunities/{opportunity_id}/participants"
    assert client.post(url, json={"user_id": str(member_b), "access": "read"}).status_code == 404
    grant = client.post(url, json={"user_id": str(member_a), "access": "read"})
    assert grant.status_code == 201

    current["principal"] = Principal(org_id=org_a, user_id=member_a, role=Role.SALES)
    assert client.get(f"/api/opportunities/{opportunity_id}").status_code == 200
    assert client.get("/api/opportunities").json()["items"][0]["id"] == opportunity_id
    assert client.post(
        f"/api/opportunities/{opportunity_id}/requirements",
        json={"original_text": "Needs private networking"},
    ).status_code == 404


def test_import_mandatory_requirements_as_unreviewed(sales_api):
    client, _, _ = sales_api
    opportunity_id = client.post("/api/opportunities", json={"title": "RFP"}).json()["id"]
    url = f"/api/opportunities/{opportunity_id}/requirements/import"
    imported = client.post(url, json={
        "text": "The service must include backups.\nThe solution shall have public access."
    })
    assert imported.status_code == 201
    assert imported.json()["created"] == 2
    assert all(row["coverage_state"] == "unreviewed" for row in imported.json()["requirements"])
    coverage = client.get(f"/api/opportunities/{opportunity_id}/coverage?limit=1").json()
    assert coverage["total"] == 2
    assert len(coverage["requirements"]) == 1
    assert coverage["mandatory_total"] == 2
    assert coverage["ready_for_quote"] is False
    assert client.post(url, json={"text": "Background context only."}).status_code == 422
