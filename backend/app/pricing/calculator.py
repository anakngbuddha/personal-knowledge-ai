"""Pure Decimal arithmetic for reproducible commercial quote lines."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.pricing.schemas import PriceObservation


class CommercialPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1, max_length=64)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    max_discount_percent: Decimal = Field(default=Decimal(0), ge=0, le=100)
    min_margin_percent: Decimal = Field(default=Decimal(0), ge=0, le=100)
    tax_percent: Decimal = Field(default=Decimal(0), ge=0, le=100)
    money_places: int = Field(default=2, ge=0, le=4)


class QuoteComponentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation: PriceObservation
    resource_quantity: Decimal = Field(gt=0)
    usage_per_resource: Decimal = Field(ge=0)
    cost_per_unit: Decimal | None = Field(default=None, ge=0)
    discount_percent: Decimal = Field(default=Decimal(0), ge=0, le=100)
    tax_percent: Decimal = Field(default=Decimal(0), ge=0, le=100)
    fx_rate: Decimal = Field(default=Decimal(1), gt=0)
    fx_source: str | None = Field(default=None, max_length=255)
    fx_at: datetime | None = None
    assumption: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def usage_required(self):
        if self.usage_per_resource == 0:
            raise ValueError("usage must be greater than zero for a priced line")
        return self


class QuoteLineResult(BaseModel):
    sku: str
    provider: str
    currency: str
    list_amount: Decimal
    discount_amount: Decimal
    sell_amount: Decimal
    cost_amount: Decimal | None
    margin_percent: Decimal | None
    tax_amount: Decimal
    total_amount: Decimal
    assumption: str
    source_ref: str
    retrieved_at: datetime
    expires_at: datetime
    blockers: list[str]


class QuoteResult(BaseModel):
    currency: str
    policy_version: str
    lines: list[QuoteLineResult]
    subtotal: Decimal
    tax_total: Decimal
    total: Decimal
    issueable: bool
    blockers: list[str]


def _money(value: Decimal, places: int) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def _usage_price(observation: PriceObservation, usage: Decimal) -> Decimal:
    if observation.unit_price is not None:
        return observation.unit_price * usage
    total = Decimal(0)
    for tier in observation.tiers:
        if usage <= tier.start:
            break
        upper = min(usage, tier.end) if tier.end is not None else usage
        total += (upper - tier.start) * tier.unit_price
    return total


def calculate_quote(
    components: list[QuoteComponentInput], policy: CommercialPolicy, *, now: datetime | None = None,
    list_price_only: bool = False,
) -> QuoteResult:
    if not components:
        raise ValueError("a quote needs at least one priced component")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    lines: list[QuoteLineResult] = []
    blockers: list[str] = []
    for index, component in enumerate(components, start=1):
        observation = component.observation
        line_blockers: list[str] = []
        if observation.currency != policy.currency and (
            component.fx_source is None or component.fx_at is None
        ):
            line_blockers.append("currency conversion source and time are required")
        if observation.currency == policy.currency and component.fx_rate != 1:
            line_blockers.append("conversion rate must be one for matching currencies")
        if component.fx_at is not None and (
            component.fx_at.tzinfo is None or component.fx_at > now
        ):
            line_blockers.append("currency conversion time is invalid")
        if observation.effective_at > now or observation.retrieved_at > now or observation.expires_at <= now:
            line_blockers.append("price observation is stale or not yet valid")
        if component.discount_percent > policy.max_discount_percent:
            line_blockers.append("discount exceeds policy")
        list_amount = _money(
            _usage_price(observation, component.usage_per_resource)
            * component.resource_quantity * component.fx_rate, policy.money_places
        )
        if list_price_only and (component.discount_percent != 0 or component.tax_percent != 0 or policy.tax_percent != 0):
            raise ValueError("list-price quotations require zero discount and tax")
        discount_amount = _money(list_amount * component.discount_percent / Decimal(100), policy.money_places)
        sell_amount = list_amount - discount_amount
        cost_amount = None if component.cost_per_unit is None else _money(
            component.cost_per_unit * component.usage_per_resource
            * component.resource_quantity * component.fx_rate, policy.money_places
        )
        margin_percent = None
        if list_price_only:
            cost_amount = None
        elif cost_amount is None:
            line_blockers.append("commercial cost is missing")
        elif sell_amount <= 0:
            line_blockers.append("selling amount must be positive")
        else:
            margin_percent = ((sell_amount - cost_amount) / sell_amount) * Decimal(100)
            if margin_percent < policy.min_margin_percent:
                line_blockers.append("margin is below policy floor")
        tax_amount = _money(sell_amount * component.tax_percent / Decimal(100), policy.money_places)
        lines.append(QuoteLineResult(
            sku=observation.sku, provider=observation.provider, currency=policy.currency,
            list_amount=list_amount, discount_amount=discount_amount, sell_amount=sell_amount,
            cost_amount=cost_amount, margin_percent=margin_percent,
            tax_amount=tax_amount, total_amount=sell_amount + tax_amount,
            assumption=component.assumption, source_ref=observation.source_ref,
            retrieved_at=observation.retrieved_at, expires_at=observation.expires_at,
            blockers=line_blockers,
        ))
        blockers.extend(f"line {index}: {reason}" for reason in line_blockers)
    subtotal = sum((line.sell_amount for line in lines), Decimal(0))
    tax_total = sum((line.tax_amount for line in lines), Decimal(0))
    return QuoteResult(
        currency=policy.currency, policy_version=policy.version, lines=lines,
        subtotal=subtotal, tax_total=tax_total, total=subtotal + tax_total,
        issueable=not blockers, blockers=blockers,
    )
