"""Deal follow-up derives bounded signals from authorized immutable sales records."""

import uuid

from app.security.labels import Role
from app.security.principal import Principal
from tests.test_opportunities import sales_api  # noqa: F401
from tests.test_sales_quotes import _setup


def test_signals_cover_requirement_gaps_and_pending_approval(sales_api):
    client, current, (_, org_b), opportunity_id, requirement_id, request = _setup(sales_api)
    url = f"/api/sales/opportunities/{opportunity_id}/signals"
    signals = client.get(url).json()["items"]
    assert signals[0]["kind"] == "missing_requirements" and signals[0]["count"] == 1
    client.patch(f"/api/opportunities/{opportunity_id}/requirements/{requirement_id}", json={
        "version": 1, "coverage_state": "covered", "coverage_note": "reviewed",
    })
    version = client.post(f"/api/sales/opportunities/{opportunity_id}/quotes", json=request).json()
    client.post(f"/api/sales/quote-versions/{version['id']}/submit")
    signals = client.get(url).json()["items"]
    assert any(signal["kind"] == "awaiting_approval" for signal in signals)
    assert not any(signal["kind"] == "missing_requirements" for signal in signals)
    assert client.get(url + "?limit=101").status_code == 422
    current["principal"] = Principal(org_id=org_b, user_id=uuid.uuid4(), role=Role.ADMIN)
    assert client.get(url).status_code == 404


def test_same_tenant_nonparticipant_cannot_read_signals(sales_api):
    client, current, (org_a, _), opportunity_id, *_ = _setup(sales_api)
    current["principal"] = Principal(org_id=org_a, user_id=uuid.uuid4(), role=Role.SALES)
    assert client.get(f"/api/sales/opportunities/{opportunity_id}/signals").status_code == 404
