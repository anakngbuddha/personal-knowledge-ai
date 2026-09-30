"""Four-provider capture and encrypted credentials require reviewed tenant mappings."""

import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from app.core.config import settings
from app.db.models import McpIntegration, ProviderSkuMap, StoredPriceObservation
from app.mcp.credentials import decrypt_secret
from app.pricing.credentials import provider_for_mapping
from app.pricing.providers.azure import UnsupportedPrice
from app.pricing.schemas import PriceObservation
from app.security.labels import Role
from app.security.principal import Principal
from tests.test_opportunities import sales_api  # noqa: F401
from tests.test_sales_quotes import _setup


@pytest.mark.parametrize("provider", ["azure", "aws", "gcp", "huawei"])
def test_capture_stores_exact_public_rate_for_each_provider(sales_api, monkeypatch, provider):
    from app.api.routes import sales_quotes
    client, current, (org_a, _), *_ = _setup(sales_api)
    current["principal"] = Principal(org_id=org_a, user_id=uuid.uuid4(), role=Role.ADMIN)
    with current["session_factory"]() as db:
        mapping = db.query(ProviderSkuMap).first()
        mapping.provider = provider
        mapping.region = "ap-southeast-5" if provider == "huawei" else "southeastasia"
        db.commit()
        map_id, service, sku, region = mapping.id, mapping.service, mapping.sku, mapping.region

    async def factory(db, principal, mapping, spec):
        assert principal.org_id == org_a

        class Provider:
            async def get_price(self, **arguments):
                assert arguments["region"] == region and arguments["entitlement_org_id"] is None
                now = datetime.now(timezone.utc)
                return PriceObservation(provider=provider, service=service, sku=sku, region=region,
                                        billing_mode="pay_per_use", unit="hour", currency="USD",
                                        unit_price="1.25", effective_at=now, retrieved_at=now,
                                        expires_at=now + timedelta(hours=1),
                                        source_ref="https://provider.example/rates", parser_version="1")
        return Provider()

    monkeypatch.setattr(sales_quotes, "provider_for_mapping", factory)
    response = client.post(f"/api/sales/sku-maps/{map_id}/capture-price", json={})
    assert response.status_code == 201, response.text
    with current["session_factory"]() as db:
        stored = db.get(StoredPriceObservation, uuid.UUID(response.json()["id"]))
        assert stored.source_kind == f"{provider}_api"
        assert stored.payload["rate_type"] == "public"
        assert stored.payload["region"] == region


def test_credentials_are_encrypted_rotatable_disabled_and_tenant_scoped(sales_api, monkeypatch):
    client, current, (org_a, org_b), *_ = _setup(sales_api)
    monkeypatch.setattr(settings, "mcp_credentials_key", Fernet.generate_key().decode())
    secret = json.dumps({"access_key_id": "A" * 20, "secret_access_key": "B" * 40})
    assert client.put("/api/sales/pricing-credentials/aws", json={"secret": secret}).status_code == 403
    current["principal"] = Principal(org_id=org_a, user_id=uuid.uuid4(), role=Role.ADMIN)
    response = client.put("/api/sales/pricing-credentials/aws", json={"secret": secret})
    assert response.status_code == 200 and response.json()["has_secret"]
    assert secret not in response.text
    with current["session_factory"]() as db:
        row = db.query(McpIntegration).filter(McpIntegration.server_slug == "pricing_aws").one()
        assert decrypt_secret(row.secret_ciphertext) == secret
        assert secret.encode() not in row.secret_ciphertext
    current["principal"] = Principal(org_id=org_b, user_id=uuid.uuid4(), role=Role.ADMIN)
    assert client.put("/api/sales/pricing-credentials/aws", json={"enabled": True}).status_code == 422
    current["principal"] = Principal(org_id=org_a, user_id=uuid.uuid4(), role=Role.ADMIN)
    assert client.put("/api/sales/pricing-credentials/aws", json={"enabled": False}).status_code == 200
    assert client.put("/api/sales/pricing-credentials/aws", json={"secret": "{}"}).status_code == 422


@pytest.mark.anyio
async def test_no_host_credential_fallback_or_cross_tenant_access(sales_api):
    _, current, (org_a, _), *_ = _setup(sales_api)
    with current["session_factory"]() as db:
        with pytest.raises(UnsupportedPrice, match="tenant pricing credentials"):
            await provider_for_mapping(db, Principal(org_id=org_a, user_id=uuid.uuid4(), role=Role.ADMIN),
                                       SimpleNamespace(provider="aws"))
