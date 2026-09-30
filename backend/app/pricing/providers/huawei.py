"""Huawei Cloud customer price inquiry for one reviewed pay-per-use resource."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.pricing.providers.azure import PricingUnavailable, UnsupportedPrice
from app.pricing.schemas import PriceObservation

HUAWEI_PRICE_URLS = {
    "intl": "https://bss-intl.myhuaweicloud.com/v2/bills/ratings/on-demand-resources",
    "eu": "https://bss.myhuaweicloud.eu/v2/bills/ratings/on-demand-resources",
}


class HuaweiRateSpec(BaseModel):
    """Dimensions copied from a reviewed Huawei calculator/API configuration."""

    model_config = ConfigDict(extra="forbid")
    market: str = Field(pattern=r"^(intl|eu)$")
    project_id: str = Field(min_length=1, max_length=64)
    cloud_service_type: str = Field(min_length=1, max_length=400)
    resource_type: str = Field(min_length=1, max_length=400)
    resource_spec: str = Field(min_length=1, max_length=400)
    region: str = Field(min_length=1, max_length=128)
    usage_factor: str = Field(min_length=1, max_length=128)
    usage_measure_id: int = Field(ge=1, le=9999)
    unit: str = Field(min_length=1, max_length=64)
    available_zone: str | None = Field(default=None, max_length=64)
    resource_size: Decimal | None = Field(default=None, gt=0)
    size_measure_id: int | None = Field(default=None, ge=1, le=9999)


def _amount(value: object) -> Decimal:
    try:
        parsed = Decimal(str(value))
        if not parsed.is_finite() or parsed < 0:
            raise InvalidOperation
        return parsed
    except (InvalidOperation, ValueError) as exc:
        raise PricingUnavailable("Huawei returned an invalid monetary amount") from exc


class HuaweiPricingProvider:
    def __init__(self, *, spec: HuaweiRateSpec, auth_token: str,
                 client: httpx.AsyncClient | None = None):
        if not auth_token or not auth_token.strip():
            raise ValueError("Huawei IAM token is required")
        if (spec.resource_size is None) != (spec.size_measure_id is None):
            raise ValueError("Huawei resource size and measure ID must be set together")
        self.spec = spec
        self.auth_token = auth_token
        self.client = client

    async def search_products(self, query: str, region: str, limit: int = 50) -> list[dict]:
        raise UnsupportedPrice("Huawei requires reviewed service, resource and specification codes")

    async def get_price(self, *, sku: str, region: str, billing_mode: str,
                        entitlement_org_id: uuid.UUID | None, meter: str | None = None) -> PriceObservation:
        spec = self.spec
        if (sku, region, billing_mode, meter) != (
            spec.resource_spec, spec.region, "pay_per_use", spec.resource_type
        ):
            raise UnsupportedPrice("Huawei price dimensions differ from the reviewed resource")
        info = {
            "id": "1", "cloud_service_type": spec.cloud_service_type,
            "resource_type": spec.resource_type, "resource_spec": spec.resource_spec,
            "region": spec.region, "usage_factor": spec.usage_factor,
            "usage_value": 1, "usage_measure_id": spec.usage_measure_id,
            "subscription_num": 1,
        }
        if spec.available_zone:
            info["available_zone"] = spec.available_zone
        if spec.resource_size is not None:
            info["resource_size"] = str(spec.resource_size)
            info["size_measure_id"] = spec.size_measure_id
        url = HUAWEI_PRICE_URLS[spec.market]
        own_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=15.0, follow_redirects=False)
        try:
            try:
                response = await client.post(
                    url, json={"project_id": spec.project_id, "product_infos": [info],
                               "inquiry_precision": 1},
                    headers={"X-Auth-Token": self.auth_token},
                )
                response.raise_for_status()
                body = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise PricingUnavailable("Huawei price inquiry API unavailable") from exc
        finally:
            if own_client:
                await client.aclose()
        if not isinstance(body, dict) or body.get("error_code"):
            raise PricingUnavailable("Huawei price inquiry returned an error")
        rows = body.get("product_rating_results")
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict) or rows[0].get("id") != "1":
            raise PricingUnavailable("Huawei response does not match the requested resource")
        row = rows[0]
        currency = body.get("currency")
        if currency != "USD" or row.get("measure_id") != 1:
            raise UnsupportedPrice("Huawei rate currency or measurement is unsupported")
        public_rate = _amount(row.get("official_website_amount"))
        contracted_rate = _amount(row.get("amount"))
        if contracted_rate > public_rate:
            raise PricingUnavailable("Huawei transaction amount exceeds website rate")
        now = datetime.now(timezone.utc)
        return PriceObservation(
            provider="huawei", service=spec.cloud_service_type,
            sku=spec.resource_spec, meter=spec.resource_type, region=spec.region,
            billing_mode="pay_per_use", unit=spec.unit, currency="USD",
            rate_type="customer_contract" if entitlement_org_id is not None else "public",
            entitlement_org_id=entitlement_org_id,
            unit_price=contracted_rate if entitlement_org_id is not None else public_rate,
            effective_at=now, retrieved_at=now, expires_at=now + timedelta(hours=1),
            source_ref=url, parser_version="1",
        )
