"""Who is asking, and what they are allowed to read.

Phase 0 (real authentication, RLS, audit log) is **not built**. What lives here is
the seam Phase 1 and Phase 2 need so that permission filtering is a real, tested
code path now rather than a retrofit later:

* every retrieval call takes a `Principal`
* the principal, not the caller, decides which sensitivity labels and accounts are
  visible
* `owner_dev` mode resolves to the single collateral owner from
  Project_Plan.md section 0, who legitimately sees everything

When Phase 0 lands, only `resolve_principal` changes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.security.labels import Role, Sensitivity, sensitivities_up_to

ALL_ACCOUNTS = "*"


@dataclass(frozen=True)
class Principal:
    org_id: uuid.UUID
    user_id: uuid.UUID | None
    role: str = Role.VIEWER
    max_sensitivity: str = Sensitivity.INTERNAL
    allow_vendor_restricted: bool = False
    # None  -> every account in the org (owner/admin)
    # set() -> no account-scoped material at all
    account_refs: frozenset[str] | None = frozenset()
    include_unapproved: bool = True
    label: str = ""
    grants: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_owner(self) -> bool:
        return self.role in (Role.OWNER, Role.ADMIN)

    @property
    def is_admin(self) -> bool:
        from app.security.labels import role_has_access
        return role_has_access(self.role, Role.ADMIN)

    @property
    def can_write_catalog(self) -> bool:
        from app.security.labels import role_has_access
        return role_has_access(self.role, Role.SOLUTIONS_ENGINEER)

    @property
    def can_manage_users(self) -> bool:
        from app.security.labels import role_has_access
        return role_has_access(self.role, Role.ADMIN)

    @property
    def can_export_restricted(self) -> bool:
        from app.security.labels import role_has_access
        return self.allow_vendor_restricted or role_has_access(self.role, Role.ADMIN)

    @property
    def sees_all_accounts(self) -> bool:
        return self.account_refs is None

    def readable_sensitivities(self) -> list[str]:
        labels = sensitivities_up_to(self.max_sensitivity)
        if self.allow_vendor_restricted:
            labels = [*labels, Sensitivity.VENDOR_RESTRICTED.value]
        return labels

    def describe(self) -> dict:
        return {
            "org_id": str(self.org_id),
            "user_id": str(self.user_id) if self.user_id else None,
            "role": self.role,
            "max_sensitivity": self.max_sensitivity,
            "allow_vendor_restricted": self.allow_vendor_restricted,
            "accounts": "all" if self.sees_all_accounts else sorted(self.account_refs or ()),
        }


def owner_principal(org_id: uuid.UUID, user_id: uuid.UUID | None = None) -> Principal:
    """The single collateral owner. Full read access by decision, not by accident."""
    return Principal(
        org_id=org_id,
        user_id=user_id,
        role=Role.OWNER,
        max_sensitivity=Sensitivity.CUSTOMER_DATA,
        allow_vendor_restricted=True,
        account_refs=None,
        include_unapproved=True,
        label="owner_dev",
    )


def restricted_principal(
    org_id: uuid.UUID,
    *,
    user_id: uuid.UUID | None = None,
    role: str = Role.SALES,
    max_sensitivity: str = Sensitivity.INTERNAL,
    allow_vendor_restricted: bool = False,
    account_refs: frozenset[str] | None = frozenset(),
    include_unapproved: bool = True,
) -> Principal:
    """Used by tests and by `dev_headers` mode. Deliberately narrow by default."""
    return Principal(
        org_id=org_id,
        user_id=user_id,
        role=role,
        max_sensitivity=max_sensitivity,
        allow_vendor_restricted=allow_vendor_restricted,
        account_refs=account_refs,
        include_unapproved=include_unapproved,
        label="restricted",
    )
