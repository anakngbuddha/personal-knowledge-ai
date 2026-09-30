"""Azure public price adapter contract and fail-closed behavior."""

import asyncio

import httpx
import pytest

from app.pricing.providers.azure import (
    AmbiguousPrice, AzurePricingProvider, PricingUnavailable, UnsupportedPrice,
)


def row(**changes):
    values = dict(
        armSkuName="Standard_D4s_v5", armRegionName="eastus", priceType="Consumption",
        meterName="D4s v5", serviceName="Virtual Machines", unitOfMeasure="1 Hour",
        currencyCode="USD", retailPrice=0.25, effectiveStartDate="2026-01-01T00:00:00Z",
        tierMinimumUnits=0,
    )
    values.update(changes)
    return values


def provider_for(pages):
    calls = []

    def handler(request: httpx.Request):
        calls.append(request)
        return httpx.Response(200, json=pages[len(calls) - 1])

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return AzurePricingProvider(client), client, calls


def test_exact_rate_and_pagination():
    provider, client, calls = provider_for([
        {"Items": [], "NextPageLink": "https://prices.azure.com/api/retail/prices?$skip=1000"},
        {"Items": [row()], "NextPageLink": None},
    ])
    try:
        result = asyncio.run(provider.get_price(
            sku="Standard_D4s_v5", region="eastus", billing_mode="pay_per_use",
            entitlement_org_id=None,
        ))
        assert result.unit_price == 0.25
        assert result.meter == "D4s v5"
        assert len(calls) == 2
        assert "armSkuName eq" in calls[0].url.params["$filter"]
        assert calls[1].url.host == "prices.azure.com"
    finally:
        asyncio.run(client.aclose())


def test_ambiguous_meter_requires_exact_selection():
    provider, client, _ = provider_for([{"Items": [row(), row(meterName="Windows")]}])
    try:
        with pytest.raises(AmbiguousPrice, match="multiple meters"):
            asyncio.run(provider.get_price(
                sku="Standard_D4s_v5", region="eastus", billing_mode="pay_per_use",
                entitlement_org_id=None,
            ))
    finally:
        asyncio.run(client.aclose())


def test_unsafe_next_page_and_tiered_rate_are_rejected():
    provider, client, _ = provider_for([{
        "Items": [], "NextPageLink": "http://127.0.0.1/private",
    }])
    try:
        with pytest.raises(PricingUnavailable, match="unsafe pagination"):
            asyncio.run(provider.search_products("Standard_D4s_v5", "eastus"))
    finally:
        asyncio.run(client.aclose())

    provider, client, _ = provider_for([{"Items": [row(tierMinimumUnits=10)]}])
    try:
        with pytest.raises(UnsupportedPrice, match="tier"):
            asyncio.run(provider.get_price(
                sku="Standard_D4s_v5", region="eastus", billing_mode="pay_per_use",
                entitlement_org_id=None,
            ))
    finally:
        asyncio.run(client.aclose())
