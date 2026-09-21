"""Translate the predicate IR into SQLAlchemy clauses.

Thin on purpose. All of the decisions live in `spec.py` and `permissions.py`; this
module only knows which column a field name maps to and how each operator is spelled
in PostgreSQL. Every value goes through SQLAlchemy binding, so nothing here can be
injected into.
"""

from __future__ import annotations

import uuid

from sqlalchemy import and_, or_
from sqlalchemy.sql.elements import ColumnElement

from app.db.models import Document
from app.retrieval.spec import Op, Predicate, PredicateSet

# Only these columns are addressable from a filter. An unknown field is a bug, not a
# no-op, because a silently dropped predicate is how permission filters disappear.
FIELD_COLUMNS = {
    "org_id": Document.org_id,
    "workspace_id": Document.workspace_id,
    "id": Document.id,
    "sensitivity": Document.sensitivity,
    "approval_state": Document.approval_state,
    "account_ref": Document.account_ref,
    "vendor": Document.vendor,
    "ownership": Document.ownership,
    "file_type": Document.file_type,
    "products_referenced": Document.products_referenced,
    "valid_until": Document.valid_until,
    "is_current": Document.is_current,
    "is_demo": Document.is_demo,
    "status": Document.status,
    "injection_flag_count": Document.injection_flag_count,
}

_UUID_FIELDS = {"org_id", "workspace_id", "id"}


class UnknownFilterField(Exception):
    pass


def compile_predicate(predicate: Predicate) -> ColumnElement:
    column = FIELD_COLUMNS.get(predicate.field)
    if column is None:
        raise UnknownFilterField(
            f"{predicate.field!r} is not a filterable column "
            f"(known: {', '.join(sorted(FIELD_COLUMNS))})"
        )

    value = predicate.value
    if predicate.op is Op.EQ:
        return column == _coerce(predicate.field, value)
    if predicate.op is Op.IN:
        values = [_coerce(predicate.field, item) for item in sorted(map(str, value or ()))]
        if not values:
            # An empty allow-list must match nothing. `IN ()` is invalid SQL and
            # `1=1` would be a silent widening, so it is spelled explicitly.
            return column.is_(None) & column.isnot(None)
        return column.in_(values)
    if predicate.op is Op.NOT_IN:
        values = [_coerce(predicate.field, item) for item in sorted(map(str, value or ()))]
        if not values:
            return column.isnot(None) | column.is_(None)
        return ~column.in_(values)
    if predicate.op is Op.IS_NULL:
        return column.is_(None)
    if predicate.op is Op.NOT_NULL:
        return column.isnot(None)
    if predicate.op is Op.IS_TRUE:
        return column.is_(True)
    if predicate.op is Op.IS_FALSE:
        return column.is_(False)
    if predicate.op is Op.CONTAINS_ANY:
        items = list(value or ())
        if not items:
            return column.is_(None) & column.isnot(None)
        # JSONB array containment, one OR per product. `products_referenced` is a
        # small array, so this is cheaper than maintaining a join table before the
        # Phase 4 product entities exist.
        return or_(*[column.contains([item]) for item in items])
    if predicate.op is Op.GTE_OR_NULL:
        # Collateral with no expiry is treated as fresh. Phase 9 replaces "no expiry"
        # with an explicit review date; until then, absent is not stale.
        return or_(column.is_(None), column >= value)
    if predicate.op is Op.IN_OR_NULL:
        values = sorted(str(item) for item in (value or ()))
        if not values:
            return column.is_(None)
        return or_(column.is_(None), column.in_(values))
    raise UnknownFilterField(f"unsupported operator: {predicate.op}")


def _coerce(field: str, value):
    if field in _UUID_FIELDS and isinstance(value, str):
        return uuid.UUID(value)
    return value


def compile_predicate_set(predicate_set: PredicateSet) -> ColumnElement:
    """AND everything together. The origin of a predicate never affects how it is
    combined: permissions and filters narrow identically, so a caller's filter can
    never widen their grants."""
    clauses = [compile_predicate(predicate) for predicate in predicate_set]
    return and_(*clauses) if clauses else and_(True)
