"""Azure public Retail Prices adapter with exact SKU and meter matching."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import httpx

from app.pricing.schemas import PriceObservation

AZURE_RETAIL_URL = "https://prices.azure.com/api/retail/prices"


class PricingUnavailable(RuntimeError):
    pass


class AmbiguousPrice(ValueError):
    pass


class UnsupportedPrice(ValueError):
    pass


def _odata_string(value: str) -> str:
    clean = value.strip()
    if not clean or len(clean) > 255 or any(ord(char) < 32 for char in clean):
        raise UnsupportedPrice("invalid Azure price filter")
    return "'" + clean.replace("'", "''") + "'"


def _checked_page_url(url: str) -> str:
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise PricingUnavailable("Azure pagination URL has an invalid port") from exc
    if parsed.scheme != "https" or parsed.hostname != "prices.azure.com" or port not in (None, 443):
        raise PricingUnavailable("Azure returned an unsafe pagination URL")
    if parsed.path != "/api/retail/prices" or parsed.username or parsed.password:
        raise PricingUnavailable("Azure returned an unexpected pagination URL")
    return url


def _parse_time(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise PricingUnavailable("Azure price has no effective date")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PricingUnavailable("Azure price has an invalid effective date") from exc
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


class AzurePricingProvider:
    def __init__(self, client: httpx.AsyncClient | None = None, *, max_pages: int = 20):
        self._client = client
        self.max_pages = max_pages

    async def _items(self, sku: str, region: str) -> list[dict]:
        filter_value = (
            f"armSkuName eq {_odata_string(sku)} and "
            f"armRegionName eq {_odata_string(region)} and priceType eq 'Consumption'"
        )
        url = AZURE_RETAIL_URL
        params: dict[str, str] | None = {"$filter": filter_value}
        items: list[dict] = []
        own_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=15.0, follow_redirects=False)
        try:
            for _ in range(self.max_pages):
                try:
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    body = response.json()
                except (httpx.HTTPError, ValueError) as exc:
                    raise PricingUnavailable("Azure Retail Prices API unavailable") from exc
                if not isinstance(body, dict) or not isinstance(body.get("Items"), list):
                    raise PricingUnavailable("Azure Retail Prices response is malformed")
                items.extend(row for row in body["Items"] if isinstance(row, dict))
                next_link = body.get("NextPageLink")
                if not next_link:
                    return items
                if not isinstance(next_link, str):
                    raise PricingUnavailable("Azure pagination URL is malformed")
                url = _checked_page_url(next_link)
                params = None
            raise PricingUnavailable("Azure pagination limit exceeded")
        finally:
            if own_client:
                await client.aclose()

    async def search_products(self, query: str, region: str, limit: int = 50) -> list[dict]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        rows = await self._items(query, region)
        matches = [row for row in rows if
                   str(row.get("armSkuName", "")).casefold() == query.casefold()
                   and str(row.get("armRegionName", "")).casefold() == region.casefold()]
        return [{
            "sku": row.get("armSkuName"), "meter": row.get("meterName"),
            "service": row.get("serviceName"), "region": row.get("armRegionName"),
        } for row in matches[:limit]]

    async def get_price(
        self, *, sku: str, region: str, billing_mode: str,
        entitlement_org_id: uuid.UUID | None, meter: str | None = None,
    ) -> PriceObservation:
        if billing_mode != "pay_per_use":
            raise UnsupportedPrice("Azure adapter currently supports consumption rates only")
        if entitlement_org_id is not None:
            raise UnsupportedPrice("Azure Retail Prices API does not return customer contract rates")
        rows = await self._items(sku, region)
        matches = [row for row in rows if
                   str(row.get("armSkuName", "")).casefold() == sku.casefold()
                   and str(row.get("armRegionName", "")).casefold() == region.casefold()
                   and row.get("priceType") == "Consumption"
                   and (meter is None or str(row.get("meterName", "")).casefold() == meter.casefold())]
        if not matches:
            raise UnsupportedPrice("Azure has no exact matching rate")
        if len(matches) != 1:
            raise AmbiguousPrice("Azure returned multiple meters; choose an exact meter")
        row = matches[0]
        try:
            tier_minimum = Decimal(str(row.get("tierMinimumUnits", 0)))
        except InvalidOperation as exc:
            raise PricingUnavailable("Azure returned an invalid tier boundary") from exc
        if tier_minimum != 0 or row.get("reservationTerm"):
            raise UnsupportedPrice("Azure tier or reservation requires a separate pricing calculation")
        if not row.get("serviceName") or not row.get("meterName") or not row.get("unitOfMeasure") or not row.get("currencyCode"):
            raise PricingUnavailable("Azure returned an incomplete rate")
        try:
            rate = Decimal(str(row["retailPrice"]))
            if not rate.is_finite() or rate < 0:
                raise InvalidOperation
        except (KeyError, InvalidOperation, ValueError) as exc:
            raise PricingUnavailable("Azure returned an invalid rate") from exc
        now = datetime.now(timezone.utc)
        return PriceObservation(
            provider="azure", service=str(row["serviceName"]),
            sku=str(row["armSkuName"]), meter=str(row["meterName"]),
            region=str(row.get("armRegionName") or region), billing_mode="pay_per_use",
            unit=str(row["unitOfMeasure"]),
            currency=str(row["currencyCode"]), rate_type="public",
            unit_price=rate, effective_at=_parse_time(row.get("effectiveStartDate")),
            retrieved_at=now, expires_at=now + timedelta(hours=12),
            source_ref=AZURE_RETAIL_URL, parser_version="1",
        )
