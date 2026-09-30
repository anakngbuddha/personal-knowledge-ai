"""Claims require explicit review and current, approved, permitted evidence on export."""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models import Document
from app.security.labels import Role
from app.security.principal import Principal
from tests.test_opportunities import sales_api  # noqa: F401


def setup(sales_api, *, approval="approved", sensitivity="public"):
    client, current, (org_a, org_b) = sales_api
    opportunity = client.post("/api/opportunities", json={"title": "Research pilot"}).json()
    with current["session_factory"]() as db:
        source = Document(org_id=org_a, workspace_id=uuid.UUID(opportunity["workspace_id"]),
                          filename="vendor.txt", original_filename="vendor.txt", file_type="txt",
                          storage_key="fixture/vendor.txt", content_hash="a" * 64,
                          status="ready", approval_state=approval, sensitivity=sensitivity,
                          source_url="https://vendor.example/security", version=1)
        db.add(source)
        db.commit()
        db.refresh(source)
        source_id = source.id
    payload = {"statement": "Vendor documents hardware key support", "competitor": "Vendor",
               "source_document_id": str(source_id), "source_anchor": "Security, section 3",
               "valid_until": (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat()}
    url = f"/api/sales/opportunities/{opportunity['id']}"
    created = client.post(url + "/claims", json=payload)
    assert created.status_code == 201, created.text
    return client, current, (org_a, org_b), source_id, created.json(), url


def reviewer(current, org_id):
    current["principal"] = Principal(org_id=org_id, user_id=uuid.uuid4(), role=Role.ADMIN)


def test_claim_needs_separate_reviewer_then_exports_citation(sales_api):
    client, current, (org_a, _), source_id, claim, url = setup(sales_api)
    assert client.get(url + "/battle-card").json()["items"] == []
    author = current["principal"].user_id
    current["principal"] = Principal(org_id=org_a, user_id=author, role=Role.ADMIN)
    decision = {"version": 1, "reason": "Checked original source section 3"}
    endpoint = f"/api/sales/claims/{claim['id']}"
    assert client.post(endpoint + "/approve", json=decision).status_code == 403
    reviewer(current, org_a)
    approved = client.post(endpoint + "/approve", json=decision)
    assert approved.status_code == 200, approved.text
    assert approved.json()["version"] == 2
    assert client.post(endpoint + "/approve", json=decision).status_code == 409
    card = client.get(url + "/battle-card").json()["items"]
    assert len(card) == 1 and card[0]["source"]["document_id"] == str(source_id)
    assert card[0]["source"]["content_hash"] == "a" * 64
    assert card[0]["source"]["anchor"] == "Security, section 3"
    assert client.post(endpoint + "/revoke", json={"version": 2, "reason": "Vendor removed support"}).status_code == 200
    assert client.get(url + "/battle-card").json()["items"] == []


def test_draft_source_cannot_support_an_approved_claim(sales_api):
    client, current, (org_a, _), _, claim, _ = setup(sales_api, approval="draft")
    reviewer(current, org_a)
    response = client.post(f"/api/sales/claims/{claim['id']}/approve", json={"version": 1, "reason": "Checked"})
    assert response.status_code == 409


def test_export_rechecks_source_version_approval_sensitivity_and_expiry(sales_api):
    client, current, (org_a, _), source_id, claim, url = setup(sales_api)
    reviewer(current, org_a)
    assert client.post(f"/api/sales/claims/{claim['id']}/approve", json={"version": 1, "reason": "Checked"}).status_code == 200
    changes = [dict(version=2), dict(content_hash="b" * 64), dict(approval_state="deprecated"),
               dict(sensitivity="confidential"), dict(valid_until=datetime.now(timezone.utc).date() - timedelta(days=1))]
    for changed in changes:
        with current["session_factory"]() as db:
            doc = db.get(Document, source_id)
            doc.version, doc.content_hash, doc.approval_state = 1, "a" * 64, "approved"
            doc.sensitivity, doc.valid_until = "public", None
            for key, value in changed.items():
                setattr(doc, key, value)
            db.commit()
        assert client.get(url + "/battle-card").json()["items"] == []


def test_claims_and_decisions_do_not_leak_across_tenants_or_participants(sales_api):
    client, current, (org_a, org_b), _, claim, url = setup(sales_api)
    for other in (Principal(org_id=org_b, user_id=uuid.uuid4(), role=Role.ADMIN),
                  Principal(org_id=org_a, user_id=uuid.uuid4(), role=Role.SALES)):
        current["principal"] = other
        assert client.get(url + "/claims").status_code == 404
        assert client.get(url + "/battle-card").status_code == 404
        assert client.post(f"/api/sales/claims/{claim['id']}/revoke", json={"version": 1, "reason": "Delete"}).status_code in (403, 404)


def test_revocation_redacts_claim_when_source_access_was_removed(sales_api):
    client, current, (org_a, _), source_id, claim, _ = setup(sales_api)
    reviewer(current, org_a)
    with current["session_factory"]() as db:
        doc = db.get(Document, source_id)
        doc.is_current = False
        db.commit()
    response = client.post(f"/api/sales/claims/{claim['id']}/revoke", json={"version": 1, "reason": "Source withdrawn"})
    assert response.status_code == 200
    assert "statement" not in response.json()


def test_source_picker_and_claim_list_recheck_source_access(sales_api):
    client, current, _, source_id, _, url = setup(sales_api)
    assert client.get(url + "/claim-sources").json()["items"][0]["id"] == str(source_id)
    with current["session_factory"]() as db:
        doc = db.get(Document, source_id)
        doc.sensitivity = "confidential"
        db.commit()
    assert client.get(url + "/claim-sources").json()["items"] == []
    assert client.get(url + "/claims").json()["items"] == []
    assert client.get(url + "/claim-sources?limit=101").status_code == 422


def test_rejected_source_deletion_preserves_bytes_and_rolls_back(monkeypatch):
    from app.core.errors import AppError
    from app.documents import service
    events = []

    def reject():
        events.append("commit")
        raise IntegrityError("delete", {}, RuntimeError("retained source"))

    db = SimpleNamespace(delete=lambda doc: events.append("delete_row"), commit=reject,
                         rollback=lambda: events.append("rollback"))
    monkeypatch.setattr(service, "get_storage", lambda: SimpleNamespace(delete=lambda key: events.append("delete_bytes")))
    with pytest.raises(AppError) as failure:
        service.delete_document(db, SimpleNamespace(storage_key="vendor.txt"))
    assert failure.value.status_code == 409
    assert events == ["delete_row", "commit", "rollback"]
