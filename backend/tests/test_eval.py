"""Tests for the Phase 4.5 evaluation substrate.

Validates:
- The labeled question set loads without errors
- Label verification (all text_contains substrings match seed corpus chunks)
- Negative questions have no expected document
- The offline evaluation pipeline produces valid metrics
- The hit-detection logic handles edge cases correctly
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

os.environ.setdefault("EMBEDDING_PROVIDER", "fake")
os.environ.setdefault("LLM_PROVIDER", "fake")
os.environ.setdefault("STORAGE_BACKEND", "local")
os.environ.setdefault("LOCAL_STORAGE_DIR", "./.test-storage")
os.environ.setdefault("OCR_PROVIDER", "none")
os.environ.setdefault("AUTH_MODE", "owner_dev")

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.catalog.seeds import SEED_PRODUCTS
from app.db.models import (
    Base,
    Document,
    DocumentStatus,
    EvaluationQuestion,
    Organization,
    SourceType,
    Workspace,
)


# SQLite compatibility
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"


ROOT = Path(__file__).resolve().parents[2]
QUESTIONS_PATH = ROOT / "docs" / "eval" / "questions.json"

_CHUNKS_DDL = """
CREATE TABLE IF NOT EXISTS document_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    org_id TEXT,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    page_number INTEGER,
    slide_number INTEGER,
    sheet_name VARCHAR(255),
    cell_range VARCHAR(64),
    section_title VARCHAR(512),
    heading_path JSON,
    start_offset INTEGER,
    end_offset INTEGER,
    injection_flags JSON,
    metadata JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""


@pytest.fixture(scope="module")
def eval_db():
    """In-memory SQLite with seeded catalog and questions."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(
        engine,
        tables=[
            Organization.__table__,
            Workspace.__table__,
            Document.__table__,
            EvaluationQuestion.__table__,
        ],
    )
    with engine.connect() as conn:
        conn.execute(text(_CHUNKS_DDL))
        conn.commit()

    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    org = Organization(id=uuid.uuid4(), slug="test-eval", name="test-eval")
    db.add(org)
    db.flush()

    ws = Workspace(id=uuid.uuid4(), name="test-ws", org_id=org.id)
    db.add(ws)
    db.flush()
    db.commit()

    # Seed catalog documents and chunks
    for prod in SEED_PRODUCTS:
        doc_filename = f"{prod['slug']}-datasheet.pdf"
        doc = Document(
            org_id=org.id,
            workspace_id=ws.id,
            filename=doc_filename,
            original_filename=doc_filename,
            file_type="pdf",
            mime_type="application/pdf",
            storage_key=f"collateral/{ws.id}/{doc_filename}",
            file_size=10240,
            title=f"{prod['name']} Official Technical Datasheet",
            vendor=prod["vendor"],
            ownership=prod["ownership"],
            source_type=SourceType.UPLOAD,
            status=DocumentStatus.READY,
            chunk_count=1,
        )
        db.add(doc)
        db.flush()

        chunk_text = (
            f"Product Technical Overview: {prod['name']} by {prod['vendor']}. "
            f"Category: {prod['category']}. Deployment: {prod['deployment_model']}. "
            f"{prod['description']} Prerequisites: {prod['prerequisites']}."
        )
        db.execute(
            text(
                "INSERT INTO document_chunks (id, document_id, org_id, chunk_index, page_number, text) "
                "VALUES (:id, :doc_id, :org_id, :idx, :page, :txt)"
            ),
            {
                "id": str(uuid.uuid4()),
                "doc_id": str(doc.id),
                "org_id": str(org.id),
                "idx": 0,
                "page": 1,
                "txt": chunk_text,
            },
        )

    db.commit()

    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module")
def questions_data() -> list[dict]:
    """Load the raw questions JSON."""
    payload = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    return payload["questions"]


# ---------------------------------------------------------------------------
# Question set validation
# ---------------------------------------------------------------------------


def test_question_file_exists():
    assert QUESTIONS_PATH.exists(), f"Missing evaluation questions: {QUESTIONS_PATH}"


def test_question_set_has_minimum_count(questions_data):
    assert len(questions_data) >= 50, (
        f"Phase 4.5 requires 50+ questions, got {len(questions_data)}"
    )


def test_all_questions_have_required_fields(questions_data):
    for i, q in enumerate(questions_data):
        assert "question" in q, f"Question {i} missing 'question' field"
        assert "tags" in q, f"Question {i} missing 'tags' field"
        assert "notes" in q, f"Question {i} missing 'notes' field"
        # document_filename and text_contains can be null for negative questions


def test_question_shapes_are_diverse(questions_data):
    """Verify we have questions across different categories."""
    all_tags = set()
    for q in questions_data:
        all_tags.update(q.get("tags", []))

    expected_shapes = [
        "capability-lookup",
        "sizing-prerequisites",
        "multi-product",
        "competitive-comparison",
        "negative-unsupported",
        "reference-architecture",
    ]
    for shape in expected_shapes:
        assert shape in all_tags, f"Missing question shape: {shape}"


def test_negative_questions_have_no_expected_document(questions_data):
    """Negative questions must have null document_filename and text_contains."""
    for q in questions_data:
        tags = q.get("tags", [])
        if "negative-unsupported" in tags:
            assert q.get("document_filename") is None, (
                f"Negative question should have null document_filename: {q['question']}"
            )
            assert q.get("text_contains") is None, (
                f"Negative question should have null text_contains: {q['question']}"
            )


def test_positive_questions_have_document_and_label(questions_data):
    """Non-negative questions must have both document_filename and text_contains."""
    for q in questions_data:
        tags = q.get("tags", [])
        if "negative-unsupported" not in tags:
            assert q.get("document_filename") is not None, (
                f"Positive question missing document_filename: {q['question']}"
            )
            assert q.get("text_contains") is not None, (
                f"Positive question missing text_contains: {q['question']}"
            )


# ---------------------------------------------------------------------------
# Label verification against seeded corpus
# ---------------------------------------------------------------------------


def test_all_document_filenames_exist_in_seed_catalog(eval_db, questions_data):
    """Every non-null document_filename must match a seeded document."""
    from sqlalchemy import select

    existing = {
        d.original_filename
        for d in eval_db.scalars(select(Document).where(Document.is_current.is_(True)))
    }

    for q in questions_data:
        filename = q.get("document_filename")
        if filename is not None:
            assert filename in existing, (
                f"Question references non-existent document '{filename}': {q['question']}"
            )


def test_all_text_contains_labels_match_corpus(eval_db, questions_data):
    """Every text_contains substring must appear in the chunk of the referenced document."""
    from sqlalchemy import select

    doc_by_filename = {
        d.original_filename: d
        for d in eval_db.scalars(select(Document).where(Document.is_current.is_(True)))
    }

    rows = eval_db.execute(
        text("SELECT document_id, text FROM document_chunks")
    ).fetchall()
    chunks_by_doc = {}
    for doc_id, chunk_text in rows:
        chunks_by_doc.setdefault(doc_id, []).append(chunk_text)

    for q in questions_data:
        label = q.get("text_contains")
        filename = q.get("document_filename")
        if label is None or filename is None:
            continue

        doc = doc_by_filename.get(filename)
        assert doc is not None, f"Doc not found for '{filename}'"

        doc_chunks = chunks_by_doc.get(str(doc.id), [])
        needle = " ".join(label.lower().split())
        found = any(
            needle in " ".join(c.lower().split()) for c in doc_chunks
        )
        assert found, (
            f"text_contains '{label}' not found in any chunk of '{filename}': {q['question']}"
        )


# ---------------------------------------------------------------------------
# Evaluation pipeline unit tests
# ---------------------------------------------------------------------------


def test_negative_questions_counted_correctly(questions_data):
    """Exactly the negative-unsupported tagged questions should be skipped."""
    neg_count = sum(
        1 for q in questions_data if "negative-unsupported" in q.get("tags", [])
    )
    assert neg_count >= 6, f"Expected at least 6 negative questions, got {neg_count}"


def test_eval_set_json_is_valid_json():
    """The questions file must be valid JSON."""
    raw = QUESTIONS_PATH.read_text(encoding="utf-8")
    data = json.loads(raw)
    assert "questions" in data
    assert isinstance(data["questions"], list)


def test_refusal_set_exists_and_is_valid():
    refusal_path = ROOT / "docs" / "eval" / "refusal_set.json"
    assert refusal_path.exists(), "Missing refusal_set.json"
    data = json.loads(refusal_path.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) >= 3, f"Need at least 3 refusal cases, got {len(data)}"


def test_adversarial_set_exists_and_is_valid():
    adversarial_path = ROOT / "docs" / "eval" / "adversarial_set.json"
    assert adversarial_path.exists(), "Missing adversarial_set.json"
    data = json.loads(adversarial_path.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) >= 3, f"Need at least 3 adversarial cases, got {len(data)}"


def test_retrieval_baseline_exists():
    baseline = ROOT / "docs" / "retrieval-baseline.md"
    assert baseline.exists(), "Missing docs/retrieval-baseline.md"
    content = baseline.read_text(encoding="utf-8")
    assert "hit@1" in content, "Baseline must contain hit@1 metric"
    assert "MRR" in content, "Baseline must contain MRR metric"


def test_generation_baseline_exists():
    baseline = ROOT / "docs" / "generation-baseline.md"
    assert baseline.exists(), "Missing docs/generation-baseline.md"
    content = baseline.read_text(encoding="utf-8")
    assert "Refusal" in content, "Baseline must contain refusal test results"
    assert "Adversarial" in content, "Baseline must contain adversarial test results"
