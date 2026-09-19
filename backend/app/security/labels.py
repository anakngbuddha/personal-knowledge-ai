"""The controlled vocabularies Project_Plan.md treats as first-class.

Kept in one dependency-free module so both ingestion and retrieval agree on the
values, and so the ordering of sensitivity is defined once instead of being
re-invented at every comparison site.
"""

from __future__ import annotations

from enum import StrEnum


class Sensitivity(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    CUSTOMER_DATA = "customer_data"
    VENDOR_RESTRICTED = "vendor_restricted"


# `vendor_restricted` is deliberately *not* on this ladder. It is an orthogonal
# flag (contractual, not hierarchical): partner terms can restrict material that
# is otherwise only `internal`. Treating it as "more secret than customer_data"
# would let a customer-data grant imply a partner-NDA grant, which is wrong.
SENSITIVITY_ORDER: tuple[Sensitivity, ...] = (
    Sensitivity.PUBLIC,
    Sensitivity.INTERNAL,
    Sensitivity.CONFIDENTIAL,
    Sensitivity.CUSTOMER_DATA,
)

DEFAULT_SENSITIVITY = Sensitivity.INTERNAL


def sensitivity_rank(value: str | Sensitivity) -> int:
    """Position on the confidentiality ladder. `vendor_restricted` ranks with
    `confidential` so it is never *less* protected than internal material."""
    if value == Sensitivity.VENDOR_RESTRICTED:
        return SENSITIVITY_ORDER.index(Sensitivity.CONFIDENTIAL)
    try:
        return SENSITIVITY_ORDER.index(Sensitivity(value))
    except ValueError as exc:  # unknown label: treat as maximally protected
        raise ValueError(f"unknown sensitivity label: {value!r}") from exc


def sensitivities_up_to(maximum: str | Sensitivity) -> list[str]:
    """Every ladder label a principal with `maximum` may read."""
    ceiling = sensitivity_rank(maximum)
    return [s.value for s in SENSITIVITY_ORDER if SENSITIVITY_ORDER.index(s) <= ceiling]


class ApprovalState(StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    DEPRECATED = "deprecated"


DEFAULT_APPROVAL_STATE = ApprovalState.DRAFT
CUSTOMER_FACING_APPROVAL_STATES = (ApprovalState.APPROVED,)


class Ownership(StrEnum):
    OWN = "own"
    RESOLD = "resold"
    UNKNOWN = "unknown"


class SourceType(StrEnum):
    UPLOAD = "upload"
    URL = "url"
    PASTE = "paste"


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    SOLUTIONS_ENGINEER = "solutions_engineer"
    SALES = "sales"
    VIEWER = "viewer"


def normalize(value: str | None, enum: type[StrEnum], default: StrEnum | None = None) -> str:
    """Parse an incoming label, falling back to `default` when one is provided.

    Unknown labels are rejected rather than coerced: silently mapping a typo to
    `public` is exactly the failure mode the sensitivity system exists to prevent.
    """
    if value is None or value == "":
        if default is None:
            raise ValueError(f"missing required {enum.__name__} value")
        return str(default)
    try:
        return str(enum(value.strip().lower()))
    except ValueError as exc:
        allowed = ", ".join(sorted(m.value for m in enum))
        raise ValueError(f"invalid {enum.__name__}: {value!r} (allowed: {allowed})") from exc
