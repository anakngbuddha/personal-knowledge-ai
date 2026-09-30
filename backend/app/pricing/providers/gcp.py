"""Google Cloud public Catalog API adapter for exact, reviewed service/SKU pairs."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

import httpx

from app.pricing.providers.azure import AmbiguousPrice, PricingUnavailable, UnsupportedPrice
from app.pricing.schemas import PriceObservation, RateTier

GCP_CATALOG_URL = "https://cloudbilling.googleapis.com/v1"


def _decimal(value: object) -> Decimal:
    try:
        result = Decimal(str(value))
        if not result.is_finite():
            raise InvalidOperation
        return result
    except (InvalidOperation, ValueError) as exc:
        raise PricingUnavailable("Google Cloud returned an invalid numeric price") from exc


def _money(value: dict) -> tuple[str, Decimal]:
    currency = value.get("currencyCode")
    if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
        raise PricingUnavailable("Google Cloud rate has no valid currency")
    amount = _decimal(value.get("units", "0")) + _decimal(value.get("nanos", 0)) / Decimal(10**9)
    if amount < 0:
        raise PricingUnavailable("Google Cloud returned a negative price")
    return currency, amount


class GoogleCloudPricingProvider:
    def __init__(self, *, service_id: str, bearer_token: str,
                 client: httpx.AsyncClient | None = None, max_pages: int = 20):
        if not re.fullmatch(r"[A-Za-z0-9-]{3,64}", service_id):
            raise ValueError("invalid Google Cloud service ID")
        if not bearer_token or not bearer_token.strip():
            raise ValueError("Google Cloud billing token is required")
        self.service_id = service_id
        self.bearer_token = bearer_token
        self.client = client
        self.max_pages = max_pages

    async def _skus(self) -> list[dict]:
        own_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=15.0, follow_redirects=False)
        url = f"{GCP_CATALOG_URL}/services/{self.service_id}/skus"
        rows: list[dict] = []
        token: str | None = None
        try:
            for _ in range(self.max_pages):
                params = {"pageSize": 5000, "currencyCode": "USD"}
                if token:
                    params["pageToken"] = token
                try:
                    response = await client.get(
                        url, params=params,
                        headers={"Authorization": f"Bearer {self.bearer_token}"},
                    )
                    response.raise_for_status()
                    body = response.json()
                except (httpx.HTTPError, ValueError) as exc:
                    raise PricingUnavailable("Google Cloud Catalog API unavailable") from exc
                if not isinstance(body, dict) or not isinstance(body.get("skus"), list):
                    raise PricingUnavailable("Google Cloud SKU response is malformed")
                rows.extend(item for item in body["skus"] if isinstance(item, dict))
                token = body.get("nextPageToken") or None
                if token is None:
                    return rows
                if not isinstance(token, str) or len(token) > 4096:
                    raise PricingUnavailable("Google Cloud pagination token is malformed")
            raise PricingUnavailable("Google Cloud SKU pagination limit exceeded")
        finally:
            if own_client:
                await client.aclose()

    async def search_products(self, query: str, region: str, limit: int = 50) -> list[dict]:
        if not 1 <= limit <= 100 or not query.strip():
            raise ValueError("invalid Google Cloud search request")
        rows = await self._skus()
        return [{"sku": row["skuId"], "service": self.service_id,
                 "description": row.get("description"), "region": region}
                for row in rows if query.casefold() in str(row.get("description", "")).casefold()
                and region in row.get("serviceRegions", []) and row.get("skuId")][:limit]

    async def get_price(self, *, sku: str, region: str, billing_mode: str,
                        entitlement_org_id: uuid.UUID | None, meter: str | None = None) -> PriceObservation:
        if billing_mode != "pay_per_use" or entitlement_org_id is not None or meter is not None:
            raise UnsupportedPrice("Google Cloud Catalog adapter supports public on-demand SKU rates")
        rows = await self._skus()
        matches = [row for row in rows if row.get("skuId") == sku and region in row.get("serviceRegions", [])]
        if not matches:
            raise UnsupportedPrice("Google Cloud has no exact SKU in this region")
        if len(matches) != 1:
            raise AmbiguousPrice("Google Cloud returned duplicate exact SKUs")
        row = matches[0]
        if row.get("category", {}).get("usageType") != "OnDemand":
            raise UnsupportedPrice("Google Cloud SKU is not on-demand")
        history = row.get("pricingInfo")
        if not isinstance(history, list) or not history:
            raise PricingUnavailable("Google Cloud SKU has no pricing information")
        try:
            selected = max(history, key=lambda item: item["effectiveTime"])
            effective = datetime.fromisoformat(selected["effectiveTime"].replace("Z", "+00:00"))
            expression = selected["pricingExpression"]
            unit = expression["usageUnit"]
            raw_tiers = expression["tieredRates"]
        except (KeyError, TypeError, ValueError) as exc:
            raise PricingUnavailable("Google Cloud pricing expression is incomplete") from exc
        if effective.tzinfo is None or not isinstance(unit, str) or not unit:
            raise PricingUnavailable("Google Cloud pricing dimensions are invalid")
        if not isinstance(raw_tiers, list) or not raw_tiers or len(raw_tiers) > 100:
            raise PricingUnavailable("Google Cloud rate tiers are invalid")
        if selected.get("aggregationInfo"):
            raise UnsupportedPrice("aggregated Google Cloud rates need a usage period policy")
        parsed: list[tuple[Decimal, Decimal]] = []
        currencies: set[str] = set()
        for tier in raw_tiers:
            if not isinstance(tier, dict) or not isinstance(tier.get("unitPrice"), dict):
                raise PricingUnavailable("Google Cloud rate tier is malformed")
            start = _decimal(tier.get("startUsageAmount"))
            currency, amount = _money(tier["unitPrice"])
            currencies.add(currency)
            parsed.append((start, amount))
        if len(currencies) != 1 or parsed[0][0] != 0 or any(
            parsed[i][0] >= parsed[i + 1][0] for i in range(len(parsed) - 1)
        ):
            raise PricingUnavailable("Google Cloud tiers or currency are inconsistent")
        now = datetime.now(timezone.utc)
        if effective > now:
            raise PricingUnavailable("Google Cloud rate is not yet effective")
        tiers = tuple(RateTier(start=start,
                               end=parsed[i + 1][0] if i + 1 < len(parsed) else None,
                               unit_price=amount)
                      for i, (start, amount) in enumerate(parsed)) if len(parsed) > 1 else ()
        return PriceObservation(
            provider="gcp", service=self.service_id, sku=sku, region=region,
            billing_mode="pay_per_use", unit=unit, currency=currencies.pop(),
            unit_price=parsed[0][1] if not tiers else None, tiers=tiers,
            effective_at=effective, retrieved_at=now, expires_at=now + timedelta(hours=12),
            source_ref=f"{GCP_CATALOG_URL}/services/{self.service_id}/skus",
            parser_version="1",
        )
