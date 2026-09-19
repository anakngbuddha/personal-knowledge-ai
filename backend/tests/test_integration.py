"""End-to-end tests against a real PostgreSQL with pgvector.

Marked `requires_db` and skipped when `DATABASE_URL` is unset, so the pure suite stays
runnable anywhere. CI supplies a PostgreSQL service container, so these are not
optional there: the permission-leak test in particular is the Phase 2 exit criterion
and must never be skipped in CI.
"""

import uuid

import pytest

from app.core.errors import DuplicateDocument
from app.db.models import Document, DocumentChunk, DocumentStatus, JobStatus, Organization
from app.documents.metadata import DocumentMetadataIn
from app.documents.service import create_document, enqueue_ingestion, process_document
from app.jobs import queue, worker
from app.retrieval.search import search
from app.retrieval.spec import RetrievalFilters
from app.security.labels import Sensitivity
from app.security.principal import owner_principal, restricted_principal
from tests import fixtures as F

pytestmark = pytest.mark.requires_db


@pytest.fixture
def org(db):
    organization = Organization(slug=f"test-{uuid.uuid4().hex[:8]}", name="Test Org")
    db.add(organization)
    db.commit()
    db.refresh(organization)
    return organization


@pytest.fixture
def owner(org):
    return owner_principal(org.id)


def ingest(db, principal, name, data, **meta):
    document = create_document(
        db,
        principal=principal,
        original_filename=name,
        data=data,
        metadata=DocumentMetadataIn(**meta),
    )
    process_document(document.id)
    db.expire_all()
    return db.get(Document, document.id)


# ------------------------------------------------------------- dedup and versioning


def test_identical_content_is_refused_as_a_duplicate(db, owner):
    data = F.MARKDOWN
    first = ingest(db, owner, "datasheet.md", data)
    assert first.status == DocumentStatus.READY
    with pytest.raises(DuplicateDocument) as excinfo:
        create_document(db, principal=owner, original_filename="copy.md", data=data)
    assert excinfo.value.existing_id == first.id


def test_reupload_of_the_same_filename_creates_a_new_version(db, owner):
    first = ingest(db, owner, "pricing.md", b"# Pricing\n\nOld numbers.\n")
    second = ingest(db, owner, "pricing.md", b"# Pricing\n\nNew numbers.\n")
    db.refresh(first)
    assert second.version == 2
    assert second.supersedes_id == first.id
    assert second.is_current is True
    assert first.is_current is False


def test_a_superseded_version_never_appears_in_retrieval(db, owner):
    ingest(db, owner, "pricing.md", b"# Pricing\n\nOrbitCloud costs 1200 dollars.\n")
    ingest(db, owner, "pricing.md", b"# Pricing\n\nOrbitCloud costs 1500 dollars.\n")
    result = search(db, principal=owner, query="OrbitCloud price", mode="keyword")
    texts = " ".join(hit.text for hit in result.hits)
    assert "1500" in texts
    assert "1200" not in texts


# --------------------------------------------------------------- citation anchors


def test_anchors_survive_the_round_trip_to_postgres(db, owner):
    document = ingest(db, owner, "deck.pptx", F.make_pptx())
    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document.id)
        .order_by(DocumentChunk.chunk_index)
        .all()
    )
    assert {chunk.slide_number for chunk in chunks} == {1, 2}
    assert any("slide 2" in (chunk.chunk_metadata or {}).get("citation", "") for chunk in chunks)

    workbook = ingest(db, owner, "pricing.xlsx", F.make_xlsx())
    sheets = {
        (chunk.sheet_name, chunk.cell_range)
        for chunk in db.query(DocumentChunk).filter(DocumentChunk.document_id == workbook.id)
    }
    assert ("Pricing", "A1:C3") in sheets


# ------------------------------------------------------ THE permission-leak test


def test_a_restricted_chunk_never_appears_in_results(db, org):
    """Phase 2 exit criterion. If this passes while the permission filter is deleted,
    the filter was never doing anything."""
    owner = owner_principal(org.id)
    ingest(
        db,
        owner,
        "acme-notes.md",
        b"# Acme\n\nAcme wants hybrid cloud and video conferencing.\n",
        sensitivity="customer_data",
        account_ref="acme",
    )
    ingest(
        db,
        owner,
        "public-overview.md",
        b"# Overview\n\nOrbitCloud provides hybrid cloud infrastructure.\n",
        sensitivity="public",
    )

    # The owner sees both.
    as_owner = search(db, principal=owner, query="hybrid cloud", mode="keyword")
    assert any("Acme" in hit.text for hit in as_owner.hits)

    # A principal capped at `internal` with no account grant sees only the public one.
    limited = restricted_principal(
        org.id, max_sensitivity=Sensitivity.INTERNAL, account_refs=frozenset()
    )
    as_limited = search(db, principal=limited, query="hybrid cloud", mode="keyword")
    assert as_limited.hits, "the public document should still be found"
    assert all("Acme" not in hit.text for hit in as_limited.hits)
    assert all(hit.sensitivity in {"public", "internal"} for hit in as_limited.hits)

    # And it is absent from the fusion inputs too, not merely filtered from the output.
    assert as_limited.candidate_count < as_owner.candidate_count


def test_a_grant_makes_account_material_visible(db, org):
    owner = owner_principal(org.id)
    ingest(
        db,
        owner,
        "acme-notes.md",
        b"# Acme\n\nAcme requires on-prem storage.\n",
        sensitivity="confidential",
        account_ref="acme",
    )
    granted = restricted_principal(
        org.id, max_sensitivity=Sensitivity.CONFIDENTIAL, account_refs=frozenset({"acme"})
    )
    ungranted = restricted_principal(
        org.id, max_sensitivity=Sensitivity.CONFIDENTIAL, account_refs=frozenset({"globex"})
    )
    assert search(db, principal=granted, query="on-prem storage", mode="keyword").hits
    assert not search(db, principal=ungranted, query="on-prem storage", mode="keyword").hits


def test_tenant_isolation(db, org):
    owner = owner_principal(org.id)
    ingest(db, owner, "secret.md", b"# Secret\n\nUnique token zzqqxx for tenant one.\n")
    other_org = Organization(slug=f"other-{uuid.uuid4().hex[:8]}", name="Other")
    db.add(other_org)
    db.commit()
    stranger = owner_principal(other_org.id)
    assert not search(db, principal=stranger, query="zzqqxx", mode="keyword").hits


# --------------------------------------------------------------- filters and modes


def test_filters_narrow_the_candidate_set_before_fusion(db, owner):
    ingest(
        db,
        owner,
        "northwind.md",
        b"# VaultStore\n\nObject storage replication for on-prem sites.\n",
        vendor="Northwind",
        ownership="resold",
        products_referenced=["VaultStore"],
    )
    ingest(
        db,
        owner,
        "ours.md",
        b"# OrbitCloud\n\nObject storage replication in the cloud.\n",
        vendor="Us",
        ownership="own",
        products_referenced=["OrbitCloud"],
    )
    unfiltered = search(db, principal=owner, query="object storage replication", mode="keyword")
    filtered = search(
        db,
        principal=owner,
        query="object storage replication",
        mode="keyword",
        filters=RetrievalFilters(vendor="Northwind"),
    )
    assert len(filtered.hits) < len(unfiltered.hits)
    assert filtered.candidate_count < unfiltered.candidate_count
    assert all(hit.vendor == "Northwind" for hit in filtered.hits)


def test_all_three_modes_run_and_report_their_branches(db, owner):
    ingest(db, owner, "caps.md", b"# OrbitCloud\n\nSupports site-to-site VPN and SSO.\n")
    for mode, expected in (
        ("vector", {"vector"}),
        ("keyword", {"keyword"}),
        ("hybrid", {"vector", "keyword"}),
    ):
        result = search(db, principal=owner, query="site-to-site VPN", mode=mode)
        assert set(result.branches) == expected
        assert result.timings_ms["total_ms"] >= 0
        assert any(p["origin"] == "permission" for p in result.predicates)


def test_draft_collateral_is_excluded_by_approved_only(db, owner):
    ingest(db, owner, "draft.md", b"# Draft\n\nMeetBridge supports call recording.\n")
    assert search(db, principal=owner, query="call recording", mode="keyword").hits
    assert not search(
        db,
        principal=owner,
        query="call recording",
        mode="keyword",
        filters=RetrievalFilters(approved_only=True),
    ).hits


# ---------------------------------------------------------------------- the queue


def test_a_queued_job_is_claimed_run_and_marked_succeeded(db, owner):
    document = create_document(
        db, principal=owner, original_filename="queued.md", data=F.MARKDOWN
    )
    enqueue_ingestion(db, document)
    assert worker.run_once(worker.worker_id(99)) is True
    db.expire_all()
    assert db.get(Document, document.id).status == DocumentStatus.READY
    counts = queue.stats(db)
    assert counts.get(JobStatus.SUCCEEDED, 0) >= 1


def test_a_permanently_bad_file_is_not_retried(db, owner):
    """A corrupt file must be buried, not retried until the attempt budget runs out."""
    document = create_document(
        db,
        principal=owner,
        original_filename="broken.md",
        data=b"# Heading only\n",
    )
    # Replace the stored object with something extraction cannot handle.
    from app.storage.factory import get_storage

    get_storage().put(document.storage_key, b"   \n\n  \n")
    enqueue_ingestion(db, document)
    worker.run_once(worker.worker_id(98))
    db.expire_all()
    job = queue.stats(db)
    assert job.get(JobStatus.DEAD, 0) >= 1
    assert db.get(Document, document.id).status == DocumentStatus.FAILED


def test_requeueing_collapses_duplicate_jobs(db, owner):
    document = create_document(
        db, principal=owner, original_filename="dupe-job.md", data=F.MARKDOWN
    )
    for _ in range(3):
        enqueue_ingestion(db, document)
    from app.db.models import IngestionJob

    live = (
        db.query(IngestionJob)
        .filter(
            IngestionJob.document_id == document.id,
            IngestionJob.status.in_([JobStatus.QUEUED, JobStatus.FAILED]),
        )
        .count()
    )
    assert live == 1


def test_injection_flags_are_recorded_on_the_document(db, owner):
    document = ingest(db, owner, "vendor-injection.md", F.INJECTION_MARKDOWN)
    assert document.status == DocumentStatus.READY, "flagged content must still ingest"
    assert document.injection_flag_count >= 1
    flagged = (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.document_id == document.id,
            DocumentChunk.injection_flags.isnot(None),
        )
        .count()
    )
    assert flagged >= 1


def test_metadata_completeness_is_queryable(db, owner):
    incomplete = ingest(db, owner, "bare.md", b"# Bare\n\nNo metadata supplied.\n")
    assert incomplete.metadata_complete is False
    assert "vendor" in incomplete.metadata_missing
    complete = ingest(
        db,
        owner,
        "curated.md",
        b"# Curated\n\nFully described.\n",
        vendor="Us",
        ownership="own",
        products_referenced=["OrbitCloud"],
        valid_until="2030-01-01",
    )
    assert complete.metadata_complete is True
    assert complete.metadata_missing is None


# ------------------------------------------------------------- Phase 3: generation


def test_generation_e2e_grounded_answer(db, owner):
    from app.generation.service import ask

    ingest(
        db,
        owner,
        "product_faq.md",
        b"# Product Specs\nOrbitCloud supports multi-region failover and 99.99% availability SLA.\n",
        vendor="Internal",
        approval_state="approved",
    )

    answer = ask(
        db,
        principal=owner,
        question="What SLA does OrbitCloud offer?",
    )
    assert not answer.refused
    assert len(answer.citations) >= 1
    assert answer.citations[0].vendor == "Internal"
    assert answer.usage is not None
    assert answer.usage.total_tokens > 0


def test_generation_e2e_refusal_when_no_context(db, owner):
    from app.generation.service import ask

    answer = ask(
        db,
        principal=owner,
        question="What is the non-existent feature XYZ-999?",
        filters={"products": ["NonExistentProduct"]},
    )
    assert answer.refused is True
    assert "insufficient" in answer.text.lower()


def test_generation_e2e_conversation_flow(db, owner):
    from app.db.models import Conversation, Message
    from app.generation.conversations import create_conversation
    from app.generation.service import ask

    conv = create_conversation(db, workspace_id=owner.workspace_id or owner.org_id)
    answer = ask(
        db,
        principal=owner,
        question="What is OrbitCloud?",
        conversation_id=str(conv.id),
    )
    assert answer.text

    messages = list(db.query(Message).filter(Message.conversation_id == conv.id).all())
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[1].role == "assistant"
    assert messages[1].prompt_version is not None
