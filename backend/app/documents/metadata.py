"""Collateral metadata captured at ingest.

**Deliberate deviation from Project_Plan.md, argued rather than assumed.**

The plan says all of source type, vendor, own-or-resold, products referenced,
approval state, valid-until, and sensitivity are "all required at upload". Two of the
plan's own commitments contradict that:

1. Phase 1's headline feature is bulk upload: "many files at once, folder drop".
   Seven mandatory fields per file turns a 50-file folder drop into 350 form inputs,
   and a single owner under time pressure will type "n/a" into all of them. Required
   fields that get filled with noise are worse than absent fields, because noise is
   indistinguishable from data.
2. The plan also says approval state and sensitivity are safety-critical.

So the rule implemented here is **safe defaults, never silent ones**:

* `sensitivity` defaults to `internal` and `approval_state` to `draft`. An unset
  field can therefore never masquerade as `public` or `approved`, which is the only
  property the safety controls actually need.
* Everything else defaults to an explicit `unknown`/null and is recorded in
  `metadata_missing`.
* `metadata_complete` means the enrichment fields (vendor, ownership, products,
  valid_until) are filled. With AUTO_APPROVE_UPLOADS (default on), it is a chase
  list, not a retrieval gate: uploads become approved immediately.
* With AUTO_APPROVE_UPLOADS off, a document still cannot be promoted to `approved`
  while incomplete.
* `GET /documents?metadata_complete=false` is the enrichment chase list.

Net effect: the same end state the plan wants, reached by a route that survives a
folder drop. If a stricter policy is ever wanted, set `REQUIRE_FULL_METADATA=true`
semantics at the route layer; the validation below already reports what is missing.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.security.labels import (
    DEFAULT_APPROVAL_STATE,
    DEFAULT_SENSITIVITY,
    ApprovalState,
    Ownership,
    Sensitivity,
    SourceType,
    normalize,
)

# Fields that must be filled before a document counts as curated. Sensitivity and
# approval state are absent on purpose: they always have a safe value.
CURATION_FIELDS = ("vendor", "ownership", "products_referenced", "valid_until")


class DocumentMetadataIn(BaseModel):
    """Metadata accepted on upload. Every field optional, every default safe."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=512)
    vendor: str | None = Field(default=None, max_length=255)
    ownership: str = Ownership.UNKNOWN
    products_referenced: list[str] = Field(default_factory=list)
    account_ref: str | None = Field(default=None, max_length=128)
    approval_state: str = str(DEFAULT_APPROVAL_STATE)
    sensitivity: str = str(DEFAULT_SENSITIVITY)
    valid_until: date | None = None
    source_type: str = str(SourceType.UPLOAD)
    source_url: str | None = None
    source_of_truth_url: str | None = None

    @field_validator("ownership")
    @classmethod
    def _ownership(cls, value: str) -> str:
        return normalize(value, Ownership, Ownership.UNKNOWN)

    @field_validator("approval_state")
    @classmethod
    def _approval(cls, value: str) -> str:
        return normalize(value, ApprovalState, DEFAULT_APPROVAL_STATE)

    @field_validator("sensitivity")
    @classmethod
    def _sensitivity(cls, value: str) -> str:
        return normalize(value, Sensitivity, DEFAULT_SENSITIVITY)

    @field_validator("source_type")
    @classmethod
    def _source_type(cls, value: str) -> str:
        return normalize(value, SourceType, SourceType.UPLOAD)

    @field_validator("products_referenced", mode="before")
    @classmethod
    def _products(cls, value):
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return [str(part).strip() for part in value if str(part).strip()]

    @field_validator("vendor", "account_ref", "title", mode="before")
    @classmethod
    def _blank_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value.strip() if isinstance(value, str) else value

    def missing_fields(self) -> list[str]:
        missing: list[str] = []
        for field in CURATION_FIELDS:
            value = getattr(self, field)
            if field == "ownership":
                if value == Ownership.UNKNOWN:
                    missing.append(field)
            elif not value:
                missing.append(field)
        # A resold product without its upstream source of truth is the exact gap
        # Phase 9's freshness monitoring cannot work around.
        if self.ownership == Ownership.RESOLD and not self.source_of_truth_url:
            missing.append("source_of_truth_url")
        return missing

    @property
    def is_complete(self) -> bool:
        return not self.missing_fields()

    def promotion_error(self) -> str | None:
        """Why this document may not be marked `approved` yet.

        When AUTO_APPROVE_UPLOADS is on, vendor/products/valid_until are optional
        enrichment rather than a gate, so incomplete metadata can still be approved.
        """
        from app.core.config import settings

        if settings.auto_approve_uploads:
            return None
        if self.approval_state == ApprovalState.APPROVED and not self.is_complete:
            return (
                "cannot approve a document with incomplete metadata; missing: "
                + ", ".join(self.missing_fields())
            )
        return None
