"""Enterprise quote gates: tenant isolation, mapping review, approval, and snapshots."""

import uuid
from datetime import datetime, timedelta, timezone

from app.db.models import McpIntegration, Product, SalesQuoteExport, SalesQuoteVersion
from app.security.labels import Role
from app.security.principal import Principal
from tests.test_opportunities import sales_api  # noqa: F401 - shared isolated database fixture


def _setup(sales_api):
    client, current, (org_a, org_b) = sales_api
    owner = current["principal"].user_id
    opportunity = client.post("/api/opportunities", json={"title": "Compute pilot"}).json()
    opportunity_id = opportunity["id"]
    requirement = client.post(
        f"/api/opportunities/{opportunity_id}/requirements",
        json={"original_text": "Four cores must be available"},
    ).json()
    with current["session_factory"]() as db:
        product = Product(
            org_id=org_a, workspace_id=uuid.UUID(opportunity["workspace_id"]),
            name="Compute", slug="compute", vendor="Azure", category="IaaS",
        )
        db.add(product)
        db.commit()
        db.refresh(product)
        product_id = str(product.id)
    current["principal"] = Principal(org_id=org_a, user_id=uuid.uuid4(), role=Role.ADMIN)
    mapping = client.post("/api/sales/sku-maps", json={
        "product_id": product_id, "provider": "azure", "service": "Virtual Machines",
        "sku": "vm-4-16", "region": "eastus", "billing_mode": "pay_per_use",
    })
    assert mapping.status_code == 201, mapping.text
    map_id = mapping.json()["id"]
    assert client.post(f"/api/sales/sku-maps/{map_id}/approve").status_code == 200
    now = datetime.now(timezone.utc)
    observation = client.post("/api/sales/price-observations/import", json={
        "sku_map_id": map_id, "commercial_cost_per_unit": "0.7", "observation": {
            "provider": "azure", "service": "Virtual Machines", "sku": "vm-4-16",
            "region": "eastus", "billing_mode": "pay_per_use", "unit": "hour",
            "currency": "USD", "unit_price": "1.25",
            "effective_at": (now - timedelta(days=1)).isoformat(),
            "retrieved_at": (now - timedelta(minutes=1)).isoformat(),
            "expires_at": (now + timedelta(days=1)).isoformat(),
            "source_ref": "https://prices.azure.com/api/retail/prices", "parser_version": "1",
        },
    })
    assert observation.status_code == 201, observation.text
    policy = client.post("/api/sales/policies", json={
        "version": "pilot-1", "currency": "USD",
    })
    assert policy.status_code == 201, policy.text
    current["principal"] = Principal(org_id=org_a, user_id=owner, role=Role.SALES)
    request = {"policy_id": policy.json()["id"], "lines": [{
        "observation_id": observation.json()["id"], "resource_quantity": "2",
        "usage_per_resource": "10", "assumption": "Two servers, ten hours",
    }]}
    assert client.get("/api/sales/policies").json()["items"][0]["id"] == request["policy_id"]
    assert client.get("/api/sales/price-observations").json()["items"][0]["id"] == request["lines"][0]["observation_id"]
    assert client.get("/api/sales/sku-maps").json()["items"][0]["id"] == map_id
    return client, current, (org_a, org_b), opportunity_id, requirement["id"], request


def test_quote_requires_coverage_then_separate_approval_and_is_immutable(sales_api):
    client, current, (org_a, _), opportunity_id, requirement_id, request = _setup(sales_api)
    url = f"/api/sales/opportunities/{opportunity_id}/quotes"
    assert client.post(url, json=request).status_code == 409
    covered = client.patch(
        f"/api/opportunities/{opportunity_id}/requirements/{requirement_id}",
        json={"version": 1, "coverage_state": "covered", "coverage_note": "Reviewed compute SKU"},
    )
    assert covered.status_code == 200, covered.text
    created = client.post(url, json=request)
    assert created.status_code == 201, created.text
    version = created.json()
    assert version["result"]["total"] == "25.00"
    assert version["result"]["tax_total"] == "0.00"
    assert version["result"]["lines"][0]["discount_amount"] == "0.00"
    version_url = f"/api/sales/quote-versions/{version['id']}"
    assert client.post(version_url + "/issue").status_code == 409
    assert client.post(version_url + "/submit").status_code == 200
    author = current["principal"].user_id
    current["principal"] = Principal(org_id=org_a, user_id=author, role=Role.ADMIN)
    assert client.post(version_url + "/approve").status_code == 403
    current["principal"] = Principal(org_id=org_a, user_id=uuid.uuid4(), role=Role.ADMIN)
    assert client.post(version_url + "/approve").status_code == 200
    assert client.post(version_url + "/issue").status_code == 200
    assert client.post(version_url + "/issue").status_code == 409
    customer = client.get(version_url + "/customer-export")
    assert customer.status_code == 200
    assert customer.json()["total"] == "25.00"
    assert "cost_amount" not in customer.text
    assert "margin_percent" not in customer.text
    repriced = client.post(f"/api/sales/quotes/{version['quote_id']}/versions", json=request)
    assert repriced.status_code == 201, repriced.text
    assert repriced.json()["number"] == 2
    assert repriced.json()["id"] != version["id"]
    assert client.get(version_url).json()["status"] == "issued"
    with current["session_factory"]() as db:
        stored = db.get(SalesQuoteVersion, uuid.UUID(version["id"]))
        assert stored.snapshot_sha256 == version["snapshot_sha256"]
        assert stored.snapshot["result"]["total"] == "25.00"


def test_cross_tenant_cannot_read_quote_or_use_price(sales_api):
    client, current, (_, org_b), opportunity_id, requirement_id, request = _setup(sales_api)
    client.patch(
        f"/api/opportunities/{opportunity_id}/requirements/{requirement_id}",
        json={"version": 1, "coverage_state": "covered", "coverage_note": "Covered"},
    )
    version = client.post(f"/api/sales/opportunities/{opportunity_id}/quotes", json=request).json()
    current["principal"] = Principal(org_id=org_b, user_id=uuid.uuid4(), role=Role.ADMIN)
    assert client.get(f"/api/sales/quote-versions/{version['id']}").status_code == 404
    assert client.post(f"/api/sales/opportunities/{opportunity_id}/quotes", json=request).status_code == 404


def test_list_price_quote_rejects_discount(sales_api):
    client, _, _, opportunity_id, requirement_id, request = _setup(sales_api)
    client.patch(
        f"/api/opportunities/{opportunity_id}/requirements/{requirement_id}",
        json={"version": 1, "coverage_state": "covered", "coverage_note": "Covered"},
    )
    request["lines"][0]["discount_percent"] = "20"
    version = client.post(f"/api/sales/opportunities/{opportunity_id}/quotes", json=request)
    assert version.status_code == 422, version.text


def test_list_price_policy_rejects_tax_and_margin(sales_api):
    client, current, (org_a, _), *_ = _setup(sales_api)
    current["principal"] = Principal(org_id=org_a, user_id=uuid.uuid4(), role=Role.ADMIN)
    for field in ("tax_percent", "max_discount_percent", "min_margin_percent"):
        response = client.post("/api/sales/policies", json={
            "version": "forbidden", "currency": "USD", field: "5",
        })
        assert response.status_code == 422


def test_google_sheets_export_is_tenant_scoped_and_idempotent(sales_api, monkeypatch):
    from app.api.routes import sales_quotes
    from app.mcp.credentials import encrypt_secret
    from app.core.config import settings

    client, current, (org_a, org_b), opportunity_id, requirement_id, request = _setup(sales_api)
    client.patch(f"/api/opportunities/{opportunity_id}/requirements/{requirement_id}",
                 json={"version": 1, "coverage_state": "covered", "coverage_note": "Reviewed"})
    version = client.post(f"/api/sales/opportunities/{opportunity_id}/quotes", json=request).json()
    url = f"/api/sales/quote-versions/{version['id']}/export/google-sheets"
    assert client.post(url).status_code == 409
    quote_url = f"/api/sales/quote-versions/{version['id']}"
    assert client.post(quote_url + "/submit").status_code == 200
    current["principal"] = Principal(org_id=org_a, user_id=uuid.uuid4(), role=Role.ADMIN)
    assert client.post(quote_url + "/approve").status_code == 200
    assert client.post(quote_url + "/issue").status_code == 200
    assert client.post(url).status_code == 409

    monkeypatch.setattr(settings, "mcp_credentials_key", "test-only-sheets-key")
    with current["session_factory"]() as db:
        db.add(McpIntegration(org_id=org_a, server_slug="google_sheets", enabled=True,
                              config={}, secret_ciphertext=encrypt_secret("tenant-secret"),
                              status="disconnected"))
        db.commit()
    calls = []
    monkeypatch.setattr(sales_quotes, "service_account_access_token", lambda secret: "access-token" if secret == "tenant-secret" else None)

    class FakeExporter:
        def __init__(self, token):
            assert token == "access-token"

        async def export(self, rows, *, title):
            calls.append((rows, title))
            assert "cost_amount" not in str(rows)
            assert "margin_percent" not in str(rows)
            return "spreadsheet-test-123456"

    monkeypatch.setattr(sales_quotes, "GoogleSheetsExporter", FakeExporter)
    first = client.post(url)
    assert first.status_code == 200, first.text
    assert first.json()["spreadsheet_id"] == "spreadsheet-test-123456"
    assert client.post(url).json() == first.json()
    assert len(calls) == 1
    current["principal"] = Principal(org_id=org_b, user_id=uuid.uuid4(), role=Role.ADMIN)
    assert client.post(url).status_code == 404
    with current["session_factory"]() as db:
        exports = db.query(SalesQuoteExport).all()
        assert len(exports) == 1 and exports[0].org_id == org_a


def test_google_sheets_export_failure_requires_admin_reconciliation(sales_api, monkeypatch):
    from app.api.routes import sales_quotes
    from app.core.config import settings
    from app.mcp.credentials import encrypt_secret
    from app.sales.sheets import SheetExportError

    client, current, (org_a, _), opportunity_id, requirement_id, request = _setup(sales_api)
    client.patch(f"/api/opportunities/{opportunity_id}/requirements/{requirement_id}",
                 json={"version": 1, "coverage_state": "covered", "coverage_note": "Reviewed"})
    version = client.post(f"/api/sales/opportunities/{opportunity_id}/quotes", json=request).json()
    quote_url = f"/api/sales/quote-versions/{version['id']}"
    client.post(quote_url + "/submit")
    current["principal"] = Principal(org_id=org_a, user_id=uuid.uuid4(), role=Role.ADMIN)
    client.post(quote_url + "/approve")
    client.post(quote_url + "/issue")
    monkeypatch.setattr(settings, "mcp_credentials_key", "test-only-sheets-key")
    with current["session_factory"]() as db:
        db.add(McpIntegration(org_id=org_a, server_slug="google_sheets", enabled=True,
                              config={}, secret_ciphertext=encrypt_secret("tenant-secret"),
                              status="disconnected"))
        db.commit()
    monkeypatch.setattr(sales_quotes, "service_account_access_token", lambda secret: "access-token")

    class FailingExporter:
        def __init__(self, token):
            pass

        async def export(self, rows, *, title):
            raise SheetExportError("provider timed out after create")

    monkeypatch.setattr(sales_quotes, "GoogleSheetsExporter", FailingExporter)
    url = quote_url + "/export/google-sheets"
    assert client.post(url).status_code == 502
    assert client.post(url).status_code == 409
    assert client.get(url).json()["status"] == "needs_reconciliation"
    result = client.post(url + "/reconcile", json={
        "outcome": "not_created", "rationale": "Checked tenant Drive and confirmed no spreadsheet exists",
    })
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "retry_authorized"

    class WorkingExporter:
        def __init__(self, token):
            pass

        async def export(self, rows, *, title):
            return "spreadsheet-recovered-12345"

    monkeypatch.setattr(sales_quotes, "GoogleSheetsExporter", WorkingExporter)
    assert client.post(url).json()["spreadsheet_id"] == "spreadsheet-recovered-12345"
    assert client.get(url).json()["status"] == "completed"
