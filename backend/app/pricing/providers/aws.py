"""AWS public Price List Query adapter with exact SKU and rate-dimension matching."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from app.pricing.providers.azure import AmbiguousPrice, PricingUnavailable, UnsupportedPrice
from app.pricing.schemas import PriceObservation, RateTier


def _positive_decimal(raw: object) -> Decimal:
    try:
        value = Decimal(str(raw))
        if not value.is_finite() or value < 0:
            raise InvalidOperation
        return value
    except (InvalidOperation, ValueError) as exc:
        raise PricingUnavailable("AWS returned an invalid price or tier boundary") from exc


class AwsPricingProvider:
    def __init__(self, *, service_code: str, client=None, max_pages: int = 20):
        if not service_code or len(service_code) > 64 or not service_code.isalnum():
            raise ValueError("invalid AWS service code")
        self.service_code = service_code
        self.client = client
        self.max_pages = max_pages

    def _client(self):
        if self.client is not None:
            return self.client
        import boto3
        return boto3.client("pricing", region_name="us-east-1")

    async def _products(self, region: str) -> list[dict]:
        if not region or len(region) > 128:
            raise ValueError("invalid AWS region")
        client = self._client()
        token: str | None = None
        rows: list[dict] = []
        for _ in range(self.max_pages):
            request = {
                "ServiceCode": self.service_code,
                "Filters": [{"Type": "TERM_MATCH", "Field": "regionCode", "Value": region}],
                "MaxResults": 100,
            }
            if token:
                request["NextToken"] = token
            try:
                response = await asyncio.to_thread(client.get_products, **request)
            except Exception as exc:  # SDK errors differ by credential/transport provider.
                raise PricingUnavailable("AWS Price List Query API unavailable") from exc
            if not isinstance(response, dict) or not isinstance(response.get("PriceList"), list):
                raise PricingUnavailable("AWS Price List response is malformed")
            for raw in response["PriceList"]:
                try:
                    item = json.loads(raw) if isinstance(raw, str) else raw
                except (TypeError, ValueError) as exc:
                    raise PricingUnavailable("AWS returned malformed product JSON") from exc
                if isinstance(item, dict):
                    rows.append(item)
            token = response.get("NextToken") or None
            if token is None:
                return rows
            if not isinstance(token, str) or len(token) > 4096:
                raise PricingUnavailable("AWS pagination token is malformed")
        raise PricingUnavailable("AWS catalog query exceeded the page limit; narrow the SKU mapping")

    async def search_products(self, query: str, region: str, limit: int = 50) -> list[dict]:
        if not 1 <= limit <= 100 or not query.strip():
            raise ValueError("invalid AWS search request")
        rows = await self._products(region)
        return [{"sku": product["sku"], "service": self.service_code,
                 "region": region, "attributes": product.get("attributes", {})}
                for row in rows if (product := row.get("product", {})).get("sku")
                and query.casefold() in json.dumps(product.get("attributes", {})).casefold()
                and product.get("attributes", {}).get("regionCode") == region][:limit]

    async def get_price(self, *, sku: str, region: str, billing_mode: str,
                        entitlement_org_id: uuid.UUID | None, meter: str | None = None) -> PriceObservation:
        if billing_mode != "pay_per_use" or entitlement_org_id is not None:
            raise UnsupportedPrice("AWS adapter supports public on-demand rates only")
        rows = await self._products(region)
        matches = [row for row in rows if row.get("product", {}).get("sku") == sku
                   and row.get("product", {}).get("attributes", {}).get("regionCode") == region]
        if not matches:
            raise UnsupportedPrice("AWS has no exact SKU in the requested region or page window")
        if len(matches) != 1:
            raise AmbiguousPrice("AWS returned duplicate exact SKUs")
        row = matches[0]
        terms = row.get("terms", {}).get("OnDemand", {})
        if not isinstance(terms, dict) or len(terms) != 1:
            raise AmbiguousPrice("AWS SKU has multiple or missing on-demand terms")
        term = next(iter(terms.values()))
        raw_dimensions = term.get("priceDimensions", {})
        if not isinstance(raw_dimensions, dict) or not raw_dimensions:
            raise PricingUnavailable("AWS SKU has no price dimensions")
        dimensions = [(key, item) for key, item in raw_dimensions.items()
                      if meter is None or key == meter or item.get("rateCode") == meter]
        if not dimensions:
            raise UnsupportedPrice("AWS meter is not present on the exact SKU")
        if meter is None and len(dimensions) > 1:
            # Multiple dimensions may be tiers of one meter; the reviewed mapping must
            # choose a rate family before those can be combined safely.
            raise AmbiguousPrice("AWS SKU has multiple price dimensions; map an exact rate code")
        if len(dimensions) != 1:
            raise AmbiguousPrice("AWS meter matches multiple price dimensions")
        rate_code, dimension = dimensions[0]
        if dimension.get("beginRange") != "0" or dimension.get("endRange") != "Inf":
            raise UnsupportedPrice("AWS tiered rate needs a complete reviewed tier family")
        unit = dimension.get("unit")
        values = dimension.get("pricePerUnit", {})
        if not unit or not isinstance(values, dict) or len(values) != 1:
            raise PricingUnavailable("AWS rate unit or currency is incomplete")
        currency, raw_price = next(iter(values.items()))
        if len(currency) != 3 or not currency.isupper():
            raise PricingUnavailable("AWS returned invalid currency")
        effective_raw = term.get("effectiveDate")
        try:
            effective = datetime.fromisoformat(effective_raw.replace("Z", "+00:00"))
        except (AttributeError, ValueError) as exc:
            raise PricingUnavailable("AWS term has no valid effective date") from exc
        if effective.tzinfo is None:
            raise PricingUnavailable("AWS effective date has no timezone")
        now = datetime.now(timezone.utc)
        if effective > now:
            raise PricingUnavailable("AWS term is not yet effective")
        return PriceObservation(
            provider="aws", service=self.service_code, sku=sku, meter=rate_code,
            region=region, billing_mode="pay_per_use", unit=unit, currency=currency,
            unit_price=_positive_decimal(raw_price), effective_at=effective,
            retrieved_at=now, expires_at=now + timedelta(hours=12),
            source_ref="https://api.pricing.us-east-1.amazonaws.com", parser_version="1",
        )
