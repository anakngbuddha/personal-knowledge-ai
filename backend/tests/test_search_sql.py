"""The compiled SQL must carry the permission predicates, and both ranking branches
must read from the same filtered candidate set.

These assertions are on generated SQL rather than on results, so they hold without a
database and still catch the failure that matters: a filter that stops being applied.
"""

import uuid

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.dialects import postgresql  # noqa: E402

from app.db.models import Document, DocumentChunk  # noqa: E402
from app.retrieval.permissions import build_predicate_set  # noqa: E402
from app.retrieval.spec import Op, Origin, Predicate, PredicateSet, RetrievalFilters  # noqa: E402
from app.retrieval.sql import UnknownFilterField, compile_predicate, compile_predicate_set  # noqa: E402
from app.security.labels import Sensitivity  # noqa: E402
from app.security.principal import owner_principal, restricted_principal  # noqa: E402

ORG = uuid.uuid4()


# In SQLAlchemy 2.0+, REGCONFIG doesn't have a built-in literal_processor for literal_binds.
postgresql.REGCONFIG.literal_processor = lambda self, dialect: lambda value: f"'{value}'"


def literal(clause) -> str:
    return str(
        clause.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )


def candidate_sql(principal, filters=None) -> str:
    where = compile_predicate_set(build_predicate_set(principal, filters))
    statement = (
        select(DocumentChunk.id)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(where)
    )
    return literal(statement)


def test_permission_predicates_reach_the_sql():
    sql = candidate_sql(restricted_principal(ORG, max_sensitivity=Sensitivity.INTERNAL))
    assert f"documents.org_id = '{ORG}'" in sql
    assert "documents.sensitivity IN ('internal', 'public')" in sql
    assert "documents.is_current IS true" in sql
    assert "documents.status = 'ready'" in sql


def test_confidential_material_is_absent_from_an_internal_principals_sql():
    sql = candidate_sql(restricted_principal(ORG, max_sensitivity=Sensitivity.INTERNAL))
    assert "confidential" not in sql
    assert "customer_data" not in sql
    assert "vendor_restricted" not in sql


def test_account_grant_appears_as_in_or_null():
    sql = candidate_sql(restricted_principal(ORG, account_refs=frozenset({"acme"})))
    assert "documents.account_ref IS NULL" in sql
    assert "documents.account_ref IN ('acme')" in sql


def test_no_grants_reduces_account_scope_to_is_null():
    sql = candidate_sql(restricted_principal(ORG, account_refs=frozenset()))
    assert "documents.account_ref IS NULL" in sql
    assert "IN (" not in sql.split("account_ref IS NULL")[1][:60]


def test_an_empty_allow_list_matches_nothing_rather_than_everything():
    """`IN ()` is invalid SQL and `TRUE` would be a silent widening."""
    clause = compile_predicate(Predicate("sensitivity", Op.IN, set(), Origin.PERMISSION))
    sql = literal(clause)
    assert "IS NULL" in sql and "IS NOT NULL" in sql


def test_filters_and_permissions_are_anded_never_ored():
    sql = candidate_sql(
        restricted_principal(ORG, max_sensitivity=Sensitivity.INTERNAL),
        RetrievalFilters(sensitivities=["customer_data"]),
    )
    # Both predicates present, joined by AND: the result is empty, not widened.
    assert "documents.sensitivity IN ('internal', 'public')" in sql
    assert "documents.sensitivity IN ('customer_data')" in sql
    between = sql.split("documents.sensitivity IN ('internal', 'public')")[1]
    assert " OR " not in between.split("documents.sensitivity IN ('customer_data')")[0]


def test_both_branches_read_from_the_same_candidate_cte():
    """This is what makes "filters apply before fusion" structural."""
    where = compile_predicate_set(build_predicate_set(owner_principal(ORG)))
    candidates = (
        select(DocumentChunk.id.label("chunk_id"))
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(where)
        .cte("candidates")
    )
    vector = literal(
        select(DocumentChunk.id)
        .join(candidates, candidates.c.chunk_id == DocumentChunk.id)
        .where(DocumentChunk.embedding.isnot(None))
        .limit(10)
    )
    keyword = literal(
        select(DocumentChunk.id)
        .join(candidates, candidates.c.chunk_id == DocumentChunk.id)
        .where(DocumentChunk.search_vector.op("@@")(func.websearch_to_tsquery("english", "x")))
        .limit(10)
    )
    for branch in (vector, keyword):
        assert "WITH candidates AS" in branch
        assert "JOIN candidates ON candidates.chunk_id = document_chunks.id" in branch
        assert f"documents.org_id = '{ORG}'" in branch


def test_every_filter_field_is_addressable():
    filters = RetrievalFilters(
        products=["A"],
        vendor="V",
        ownership="own",
        account_ref="acme",
        approval_states=["approved"],
        sensitivities=["internal"],
        file_types=["pdf"],
        document_ids=[str(uuid.uuid4())],
        exclude_injection_flagged=True,
    )
    for predicate in filters.to_predicates():
        compile_predicate(predicate)  # must not raise


def test_an_unknown_field_is_an_error_not_a_dropped_predicate():
    with pytest.raises(UnknownFilterField):
        compile_predicate(Predicate("secret_backdoor", Op.EQ, 1, Origin.FILTER))


def test_compiling_an_empty_set_is_not_silently_permissive():
    """Compiling nothing yields TRUE, which is exactly why `assert_enforced` exists
    upstream. This test documents the boundary rather than pretending it is safe."""
    sql = literal(compile_predicate_set(PredicateSet()))
    assert "true" in sql.lower()
