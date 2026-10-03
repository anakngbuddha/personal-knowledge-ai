"""Battle Quote setup exposes reviewable tenant data without disclosing secrets."""

import uuid

import pytest

from app.db.models import McpIntegration, Product, ProviderSkuMap
from app.security.labels import Role
from app.security.principal import Principal
from tests.test_opportunities import sales_api  # noqa: F401
from tests.test_sales_quotes import _setup


@pytest.mark.parametrize("endpoint", ["pricing-credentials", "pricing-products", "sku-maps?status=draft"])
def test_tenant_setup_reads_require_administrator(sales_api, endpoint):
    client, current, (org_a, _) = sales_api
    assert client.get(f"/api/sales/{endpoint}").status_code == 403
    current["principal"] = Principal(org_id=org_a, user_id=None, role=Role.ADMIN)
    assert client.get(f"/api/sales/{endpoint}").status_code == 403


def test_credential_status_is_tenant_scoped_and_never_returns_secret(sales_api):
    client, current, (org_a, org_b) = sales_api
    current["principal"] = Principal(org_id=org_a, user_id=uuid.uuid4(), role=Role.ADMIN)
    with current["session_factory"]() as db:
        db.add_all([
            McpIntegration(org_id=org_a, server_slug="pricing_aws", enabled=False,
                           secret_ciphertext=b"tenant-a-encrypted-secret", config={}),
            McpIntegration(org_id=org_b, server_slug="pricing_gcp", enabled=True,
                           secret_ciphertext=b"tenant-b-encrypted-secret", config={}),
        ])
        db.commit()
    response = client.get("/api/sales/pricing-credentials")
    assert response.status_code == 200
    by_provider = {row["provider"]: row for row in response.json()["items"]}
    assert set(by_provider) == {"azure", "aws", "gcp", "huawei"}
    assert by_provider["azure"] == {"provider": "azure", "enabled": True, "has_secret": False,
                                    "requires_credentials": False}
    assert by_provider["aws"]["has_secret"] and not by_provider["aws"]["enabled"]
    assert not by_provider["gcp"]["has_secret"]
    assert "encrypted-secret" not in response.text
    assert all(set(row) == {"provider", "enabled", "has_secret", "requires_credentials"}
               for row in by_provider.values())


def test_draft_mapping_queue_is_tenant_scoped_and_approval_moves_it(sales_api):
    client, current, (org_a, org_b), *_ = _setup(sales_api)
    current["principal"] = Principal(org_id=org_a, user_id=uuid.uuid4(), role=Role.ADMIN)
    with current["session_factory"]() as db:
        mapping = db.query(ProviderSkuMap).filter(ProviderSkuMap.org_id == org_a).one()
        mapping.status = "draft"
        mapping_id = str(mapping.id)
        db.add(ProviderSkuMap(org_id=org_b, product_id=mapping.product_id,
                             provider="aws", service="AmazonEC2", sku="foreign-sku", region="ap-southeast-1",
                             billing_mode="pay_per_use", status="draft"))
        db.commit()
    queue = client.get("/api/sales/sku-maps?status=draft&limit=1").json()
    assert [row["id"] for row in queue["items"]] == [mapping_id]
    assert client.get("/api/sales/sku-maps?status=draft&offset=1").json()["items"] == []
    assert client.get("/api/sales/sku-maps").json()["items"] == []
    assert client.post(f"/api/sales/sku-maps/{mapping_id}/approve").status_code == 200
    assert client.get("/api/sales/sku-maps?status=draft").json()["items"] == []
    assert client.get("/api/sales/sku-maps").json()["items"][0]["id"] == mapping_id
    current["principal"] = Principal(org_id=org_a, user_id=uuid.uuid4(), role=Role.SALES)
    assert client.get("/api/sales/sku-maps").status_code == 200
    assert client.get("/api/sales/sku-maps?status=draft").status_code == 403


def test_pricing_products_only_include_eligible_tenant_products_and_paginate(sales_api):
    client, current, (org_a, org_b) = sales_api
    current["principal"] = Principal(org_id=org_a, user_id=uuid.uuid4(), role=Role.ADMIN)
    with current["session_factory"]() as db:
        for name, org_id, curation, lifecycle in [
            ("Azure Compute", org_a, "confirmed", "GA"),
            ("GCP Compute", org_a, "confirmed", "GA"),
            ("Suggested product", org_a, "suggested", "GA"),
            ("Retired product", org_a, "confirmed", "EOL"),
            ("Other tenant", org_b, "confirmed", "GA"),
        ]:
            db.add(Product(org_id=org_id, workspace_id=uuid.uuid4(), name=name,
                           slug=name.lower().replace(" ", "-"), vendor="Cloud", category="IaaS",
                           curation_status=curation, lifecycle_status=lifecycle))
        db.commit()
    first = client.get("/api/sales/pricing-products?limit=1").json()
    assert [row["name"] for row in first["items"]] == ["Azure Compute"]
    assert set(first["items"][0]) == {"id", "name", "vendor"}
    second = client.get("/api/sales/pricing-products?limit=1&offset=1").json()
    assert [row["name"] for row in second["items"]] == ["GCP Compute"]
    assert client.get("/api/sales/pricing-products?offset=2").json()["items"] == []


@pytest.mark.parametrize("path", ["sku-maps?status=unknown", "sku-maps?limit=101",
                                 "pricing-products?offset=-1", "pricing-products?limit=101"])
def test_setup_filters_and_pagination_are_validated(sales_api, path):
    client, current, (org_a, _) = sales_api
    current["principal"] = Principal(org_id=org_a, user_id=uuid.uuid4(), role=Role.ADMIN)
    assert client.get(f"/api/sales/{path}").status_code == 422
