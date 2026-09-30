"""Huawei pay-per-use inquiry contract fixtures."""

import uuid
from decimal import Decimal

import httpx
import pytest

from app.pricing.providers.azure import UnsupportedPrice
from app.pricing.providers.huawei import HuaweiPricingProvider, HuaweiRateSpec


def spec():
    return HuaweiRateSpec(
        market="intl", project_id="project-1", cloud_service_type="hws.service.type.ec2",
        resource_type="hws.resource.type.vm", resource_spec="c3.3xlarge.2.linux",
        region="ap-southeast-1", usage_factor="Duration", usage_measure_id=4, unit="hour",
    )


@pytest.mark.anyio
async def test_huawei_public_and_contract_amounts_are_distinct():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={
            "currency": "USD", "product_rating_results": [{
                "id": "1", "product_id": "provider-product-1", "measure_id": 1,
                "official_website_amount": "1.2", "amount": "0.9",
            }],
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        provider = HuaweiPricingProvider(spec=spec(), auth_token="test-token", client=client)
        arguments = dict(sku="c3.3xlarge.2.linux", region="ap-southeast-1",
                         billing_mode="pay_per_use", meter="hws.resource.type.vm")
        public = await provider.get_price(**arguments, entitlement_org_id=None)
        org_id = uuid.uuid4()
        contract = await provider.get_price(**arguments, entitlement_org_id=org_id)
    assert public.unit_price == Decimal("1.2") and public.rate_type == "public"
    assert contract.unit_price == Decimal("0.9") and contract.entitlement_org_id == org_id
    assert requests[0].headers["X-Auth-Token"] == "test-token"
    assert requests[0].url.host == "bss-intl.myhuaweicloud.com"
    assert '"usage_value":1' in requests[0].content.decode()


@pytest.mark.anyio
async def test_huawei_rejects_other_spec_without_calling_provider():
    calls = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: calls.append(request) or httpx.Response(200, json={})
    )) as client:
        provider = HuaweiPricingProvider(spec=spec(), auth_token="test-token", client=client)
        with pytest.raises(UnsupportedPrice):
            await provider.get_price(sku="other", region="ap-southeast-1",
                                     billing_mode="pay_per_use", meter="hws.resource.type.vm",
                                     entitlement_org_id=None)
    assert calls == []
