"""Recorded-shape Google Cloud public Catalog API contract tests."""

import json

import httpx
import pytest

from app.pricing.providers.azure import UnsupportedPrice
from app.pricing.providers.gcp import GoogleCloudPricingProvider


@pytest.mark.anyio
async def test_exact_gcp_sku_after_pagination_and_tier_math():
    calls = []

    def respond(request: httpx.Request):
        calls.append(request)
        if "pageToken=second" not in str(request.url):
            return httpx.Response(200, json={"skus": [{"skuId": "other"}], "nextPageToken": "second"})
        return httpx.Response(200, json={"skus": [{
            "skuId": "D041-B8A1-6E0B", "serviceRegions": ["us-east1"],
            "category": {"usageType": "OnDemand"},
            "pricingInfo": [{"effectiveTime": "2025-01-01T00:00:00Z", "pricingExpression": {
                "usageUnit": "h", "displayQuantity": 100,
                "tieredRates": [
                    {"startUsageAmount": 0, "unitPrice": {"currencyCode": "USD", "units": "0", "nanos": 100000000}},
                    {"startUsageAmount": 100, "unitPrice": {"currencyCode": "USD", "units": "0", "nanos": 50000000}},
                ],
            }}],
        }]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        provider = GoogleCloudPricingProvider(service_id="6F81-5844-456A", bearer_token="test", client=client)
        rate = await provider.get_price(sku="D041-B8A1-6E0B", region="us-east1",
                                        billing_mode="pay_per_use", entitlement_org_id=None)
    assert rate.provider == "gcp"
    assert rate.unit == "h"
    assert rate.unit_price is None
    assert [str(t.unit_price) for t in rate.tiers] == ["0.1", "0.05"]
    assert rate.tiers[0].end == 100
    assert len(calls) == 2
    assert all(call.headers["Authorization"] == "Bearer test" for call in calls)


@pytest.mark.anyio
async def test_gcp_rejects_wrong_region_and_contract_rate():
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json={"skus": [{"skuId": "one", "serviceRegions": ["eu-west1"]}]})
    )) as client:
        provider = GoogleCloudPricingProvider(service_id="6F81-5844-456A", bearer_token="test", client=client)
        with pytest.raises(UnsupportedPrice):
            await provider.get_price(sku="one", region="us-east1", billing_mode="pay_per_use",
                                     entitlement_org_id=None)
        with pytest.raises(UnsupportedPrice):
            await provider.get_price(sku="one", region="eu-west1", billing_mode="pay_per_use",
                                     entitlement_org_id=__import__("uuid").uuid4())
