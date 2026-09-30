"""AWS Price List Query contract fixtures without live credentials."""

import json

import pytest

from app.pricing.providers.aws import AwsPricingProvider
from app.pricing.providers.azure import AmbiguousPrice, UnsupportedPrice


def _price(sku="SKU-1", region="us-east-1", *, dimensions=None):
    dimensions = dimensions or {"SKU-1.JRTCKXETXF.RATE": {
        "rateCode": "SKU-1.JRTCKXETXF.RATE", "unit": "Hrs", "beginRange": "0",
        "endRange": "Inf", "pricePerUnit": {"USD": "0.42"},
    }}
    return json.dumps({
        "product": {"sku": sku, "attributes": {"regionCode": region, "instanceType": "m5.large"}},
        "terms": {"OnDemand": {f"{sku}.JRTCKXETXF": {
            "effectiveDate": "2025-01-01T00:00:00Z", "priceDimensions": dimensions,
        }}},
    })


class StubPricingClient:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get_products(self, **kwargs):
        self.calls.append(kwargs)
        return self.pages.pop(0)


@pytest.mark.anyio
async def test_aws_exact_sku_region_and_rate_after_pagination():
    client = StubPricingClient([
        {"PriceList": [_price(sku="OTHER")], "NextToken": "page2"},
        {"PriceList": [_price()], "NextToken": None},
    ])
    provider = AwsPricingProvider(service_code="AmazonEC2", client=client)
    rate = await provider.get_price(sku="SKU-1", region="us-east-1",
                                    billing_mode="pay_per_use", entitlement_org_id=None,
                                    meter="SKU-1.JRTCKXETXF.RATE")
    assert rate.provider == "aws"
    assert str(rate.unit_price) == "0.42"
    assert rate.unit == "Hrs"
    assert client.calls[1]["NextToken"] == "page2"
    assert client.calls[0]["Filters"][0]["Value"] == "us-east-1"


@pytest.mark.anyio
async def test_aws_rejects_mismatched_sku_and_ambiguous_dimensions():
    provider = AwsPricingProvider(service_code="AmazonEC2", client=StubPricingClient([
        {"PriceList": [_price()], "NextToken": None},
    ]))
    with pytest.raises(UnsupportedPrice):
        await provider.get_price(sku="OTHER", region="us-east-1", billing_mode="pay_per_use",
                                 entitlement_org_id=None)

    dimensions = {
        "rate-a": {"rateCode": "rate-a", "unit": "Hrs", "beginRange": "0", "endRange": "Inf",
                   "pricePerUnit": {"USD": "0.42"}},
        "rate-b": {"rateCode": "rate-b", "unit": "Hrs", "beginRange": "0", "endRange": "Inf",
                   "pricePerUnit": {"USD": "0.52"}},
    }
    provider = AwsPricingProvider(service_code="AmazonEC2", client=StubPricingClient([
        {"PriceList": [_price(dimensions=dimensions)], "NextToken": None},
    ]))
    with pytest.raises(AmbiguousPrice):
        await provider.get_price(sku="SKU-1", region="us-east-1", billing_mode="pay_per_use",
                                 entitlement_org_id=None)
