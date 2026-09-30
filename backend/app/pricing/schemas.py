"""Shared price contract for provider adapters and the commercial calculator."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RateTier(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: Decimal = Field(ge=0)
    end: Decimal | None = Field(default=None, gt=0)
    unit_price: Decimal = Field(ge=0)

    @model_validator(mode="after")
    def ordered(self):
        if self.end is not None and self.end <= self.start:
            raise ValueError("tier end must exceed start")
        return self


class PriceObservation(BaseModel):
    """Immutable provider rate as observed at one point in time."""

    model_config = ConfigDict(extra="forbid")

    provider: Literal["huawei", "aws", "azure", "gcp"]
    service: str = Field(min_length=1, max_length=128)
    sku: str = Field(min_length=1, max_length=255)
    meter: str | None = Field(default=None, max_length=255)
    region: str = Field(min_length=1, max_length=128)
    billing_mode: str = Field(min_length=1, max_length=64)
    unit: str = Field(min_length=1, max_length=64)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    rate_type: Literal["public", "partner", "customer_contract"] = "public"
    unit_price: Decimal | None = Field(default=None, ge=0)
    tiers: tuple[RateTier, ...] = ()
    effective_at: datetime
    retrieved_at: datetime
    expires_at: datetime
    source_ref: str = Field(min_length=1, max_length=2048)
    parser_version: str = Field(min_length=1, max_length=32)
    entitlement_org_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def coherent(self):
        if (self.unit_price is None) != bool(self.tiers):
            raise ValueError("exactly one of unit_price or tiers is required")
        if any(value.tzinfo is None for value in (self.effective_at, self.retrieved_at, self.expires_at)):
            raise ValueError("price timestamps must include a timezone")
        if self.expires_at <= self.retrieved_at:
            raise ValueError("expires_at must follow retrieved_at")
        if self.rate_type != "public" and self.entitlement_org_id is None:
            raise ValueError("non-public price requires tenant entitlement")
        if self.tiers:
            expected = Decimal(0)
            for index, tier in enumerate(self.tiers):
                if tier.start != expected:
                    raise ValueError("tiers must be contiguous and start at zero")
                if tier.end is None:
                    if index != len(self.tiers) - 1:
                        raise ValueError("open-ended tier must be last")
                    break
                expected = tier.end
            if self.tiers[-1].end is not None:
                raise ValueError("final tier must be open-ended")
        return self


class PricingProvider(Protocol):
    async def search_products(self, query: str, region: str, limit: int = 50) -> list[dict]: ...

    async def get_price(
        self, *, sku: str, region: str, billing_mode: str, entitlement_org_id: uuid.UUID | None,
        meter: str | None = None,
    ) -> PriceObservation: ...
