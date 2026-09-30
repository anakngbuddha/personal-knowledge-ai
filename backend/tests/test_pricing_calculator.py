"""Provider price contract and deterministic commercial arithmetic."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.pricing.calculator import CommercialPolicy, QuoteComponentInput, calculate_quote
from app.pricing.schemas import PriceObservation, RateTier

NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)


def observation(**changes):
    values = dict(
        provider="azure", service="Virtual Machines", sku="vm-4-16", region="eastus",
        billing_mode="pay_per_use", unit="hour", currency="USD", unit_price=Decimal("1.25"),
        effective_at=NOW - timedelta(days=1), retrieved_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(hours=12), source_ref="https://example.com/price",
        parser_version="1",
    )
    values.update(changes)
    return PriceObservation(**values)


def policy(**changes):
    values = dict(version="policy-1", currency="USD", max_discount_percent=Decimal("10"),
                  min_margin_percent=Decimal("20"))
    values.update(changes)
    return CommercialPolicy(**values)


def test_exact_line_arithmetic_and_reproducibility():
    item = QuoteComponentInput(
        observation=observation(), resource_quantity=Decimal(2),
        usage_per_resource=Decimal(10), cost_per_unit=Decimal("0.70"),
        discount_percent=Decimal(10), tax_percent=Decimal(5),
        assumption="Two servers for ten hours",
    )
    first = calculate_quote([item], policy(), now=NOW)
    second = calculate_quote([item], policy(), now=NOW)
    assert first == second
    assert first.issueable
    assert first.lines[0].list_amount == Decimal("25.00")
    assert first.lines[0].discount_amount == Decimal("2.50")
    assert first.lines[0].cost_amount == Decimal("14.00")
    assert first.subtotal == Decimal("22.50")
    assert first.tax_total == Decimal("1.13")
    assert first.total == Decimal("23.63")


def test_tiered_rate_and_policy_blockers():
    rate = observation(
        unit_price=None,
        tiers=(RateTier(start=0, end=10, unit_price=Decimal("2")),
               RateTier(start=10, end=None, unit_price=Decimal("1"))),
    )
    item = QuoteComponentInput(
        observation=rate, resource_quantity=1, usage_per_resource=15,
        cost_per_unit=Decimal("2"), discount_percent=Decimal(20),
        assumption="15 units",
    )
    result = calculate_quote([item], policy(), now=NOW)
    assert result.lines[0].list_amount == Decimal("25.00")
    assert not result.issueable
    assert "line 1: discount exceeds policy" in result.blockers
    assert "line 1: margin is below policy floor" in result.blockers


def test_missing_cost_stale_price_and_fx_provenance_block_issue():
    item = QuoteComponentInput(
        observation=observation(currency="EUR", expires_at=NOW - timedelta(seconds=1)),
        resource_quantity=1, usage_per_resource=10, assumption="Ten hours",
    )
    result = calculate_quote([item], policy(), now=NOW)
    assert not result.issueable
    assert any("commercial cost is missing" in reason for reason in result.blockers)
    assert any("stale" in reason for reason in result.blockers)
    assert any("conversion source" in reason for reason in result.blockers)


def test_observation_rejects_ambiguous_rate_and_tier_gaps():
    with pytest.raises(ValidationError, match="exactly one"):
        observation(unit_price=None)
    with pytest.raises(ValidationError, match="contiguous"):
        observation(unit_price=None, tiers=(RateTier(start=1, end=None, unit_price=1),))
    with pytest.raises(ValidationError, match="tenant entitlement"):
        observation(rate_type="customer_contract")
