"""Offline retrieval evaluation: runs against SQLite with seeded catalog data.

    python scripts/run_eval_offline.py --out docs/retrieval-baseline.md

Unlike run_eval.py (which requires PostgreSQL + pgvector for real vector/FTS
search), this script seeds an in-memory SQLite database with the Phase 4 catalog,
loads the labeled question set, and measures retrieval against the fake embedding
provider using pure-Python substring matching.

This is the **plumbing baseline**: it validates that the eval pipeline, question
labels, and scoring logic work end-to-end. A meaningful quality baseline requires
a PostgreSQL instance with real embeddings (run_eval.py).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("LLM_PROVIDER", "fake")
os.environ.setdefault("EMBEDDING_PROVIDER", "fake")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

# ---------------------------------------------------------------------------
# SQLite compatibility: compile PG-only types to SQLite equivalents.
# Must be registered BEFORE importing models so create_all sees them.
# ---------------------------------------------------------------------------
from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402


@compiles(JSONB, "sqlite")  # type: ignore[no-untyped-call]
def _compile_jsonb_sqlite(element, compiler, **kw):  # type: ignore[no-untyped-def]
    return "JSON"


from sqlalchemy import create_engine, event, select, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.models import (  # noqa: E402
    Base,
    Document,
    DocumentChunk,
    DocumentStatus,
    EvaluationQuestion,
    Organization,
    SourceType,
    Workspace,
)

# ---------------------------------------------------------------------------
# Raw DDL for document_chunks in SQLite (no Computed/TSVECTOR/Vector columns)
# ---------------------------------------------------------------------------
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


def _setup_db() -> tuple[Session, Organization, Workspace]:
    """Create an in-memory SQLite DB with tables and seed data."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_fk(conn, _):  # type: ignore[no-untyped-def]
        conn.execute("PRAGMA foreign_keys=ON")

    # Create only the tables that have no PG-specific computed columns
    Base.metadata.create_all(
        engine,
        tables=[
            Organization.__table__,
            Workspace.__table__,
            Document.__table__,
            # DocumentChunk is created via raw DDL below (TSVECTOR/Vector issue)
            EvaluationQuestion.__table__,
        ],
    )
    # Create document_chunks manually without TSVECTOR and Vector columns
    with engine.connect() as conn:
        conn.execute(text(_CHUNKS_DDL))
        conn.commit()

    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    org = Organization(id=uuid.uuid4(), slug="eval-org", name="eval-org")
    db.add(org)
    db.flush()

    ws = Workspace(id=uuid.uuid4(), name="eval-workspace", org_id=org.id)
    db.add(ws)
    db.flush()
    db.commit()
    return db, org, ws


def _seed_catalog(db: Session, org: Organization, ws: Workspace) -> int:
    """Seed the synthetic catalog documents and chunks from seeds.py data.

    Returns the number of documents+chunks created.
    """
    from app.catalog.seeds import SEED_PRODUCTS  # noqa: E402

    count = 0
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
        # Insert chunk via raw SQL to avoid ORM trying to set embedding/search_vector
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
        count += 1

    db.commit()
    return count


def _load_questions(db: Session, questions_path: Path) -> list[EvaluationQuestion]:
    """Load labeled questions into the evaluation_questions table."""
    payload = json.loads(questions_path.read_text(encoding="utf-8"))
    questions_data = payload["questions"] if isinstance(payload, dict) else payload

    by_filename: dict[str, Document] = {
        d.original_filename: d
        for d in db.scalars(select(Document).where(Document.is_current.is_(True)))
    }

    loaded: list[EvaluationQuestion] = []
    unresolved: list[str] = []
    for item in questions_data:
        filename = item.get("document_filename")
        doc = by_filename.get(filename) if filename else None
        if filename and doc is None:
            unresolved.append(filename)

        eq = EvaluationQuestion(
            question=item["question"],
            expected_document_id=doc.id if doc else None,
            expected_page_number=item.get("page_number"),
            expected_text_contains=item.get("text_contains"),
            tags=item.get("tags"),
            notes=item.get("notes"),
        )
        db.add(eq)
        loaded.append(eq)
    db.commit()

    for eq in loaded:
        db.refresh(eq)

    if unresolved:
        print(
            f"  WARNING: {len(set(unresolved))} document(s) not found in seeded catalog: "
            + ", ".join(sorted(set(unresolved)))
        )
    return loaded


def _get_chunks(db: Session) -> list[dict]:
    """Fetch all chunks as dicts via raw SQL (avoids ORM mapped Vector/TSVECTOR)."""
    rows = db.execute(
        text("SELECT id, document_id, org_id, chunk_index, page_number, text FROM document_chunks")
    ).fetchall()
    return [
        {
            "id": r[0],
            "document_id": r[1],
            "org_id": r[2],
            "chunk_index": r[3],
            "page_number": r[4],
            "text": r[5],
        }
        for r in rows
    ]


def _is_hit(question: EvaluationQuestion, chunk: dict) -> bool:
    """Check if a chunk matches the question's expected label."""
    if question.expected_text_contains:
        needle = " ".join(question.expected_text_contains.lower().split())
        haystack = " ".join(chunk["text"].lower().split())
        if needle in haystack:
            return True
        if question.expected_document_id and str(question.expected_document_id) == chunk["document_id"]:
            if question.expected_page_number and chunk["page_number"] == question.expected_page_number:
                return True
        return False
    if question.expected_document_id:
        return str(question.expected_document_id) == chunk["document_id"]
    return False


def _evaluate_offline(
    questions: list[EvaluationQuestion],
    all_chunks: list[dict],
    top_k: int = 8,
) -> dict:
    """Run offline evaluation using fake cosine similarity scoring.

    Scores chunks using fake embedding cosine similarity, then checks
    whether the correct passage appears in the top-K results.
    """
    from app.embeddings.factory import get_embedding_provider  # noqa: E402

    provider = get_embedding_provider()

    hits_at = {1: 0, 5: 0, top_k: 0}
    reciprocal = 0.0
    negative = 0
    label_verified = 0

    for question in questions:
        if not (question.expected_text_contains or question.expected_document_id):
            negative += 1
            continue

        # Score chunks by fake cosine similarity
        q_vec = provider.embed_query(question.question)
        scored: list[tuple[float, dict]] = []
        for chunk in all_chunks:
            c_vec = provider.embed_query(chunk["text"])
            dot = sum(a * b for a, b in zip(q_vec, c_vec))
            scored.append((dot, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_hits = scored[:top_k]

        # Verify label exists in corpus at all (not just in top-K)
        exists_anywhere = any(_is_hit(question, chunk) for _, chunk in scored)
        if exists_anywhere:
            label_verified += 1

        rank = next(
            (i for i, (_, chunk) in enumerate(top_hits, start=1) if _is_hit(question, chunk)),
            None,
        )
        if rank:
            reciprocal += 1.0 / rank
            for cutoff in hits_at:
                if rank <= cutoff:
                    hits_at[cutoff] += 1

    total = len(questions) - negative
    return {
        "mode": "offline-fake-cosine",
        "questions": total,
        "negative_skipped": negative,
        "labels_verified": label_verified,
        "labels_unverified": total - label_verified,
        "hit@1": hits_at[1] / total if total else 0.0,
        "hit@5": hits_at[5] / total if total else 0.0,
        f"hit@{top_k}": hits_at[top_k] / total if total else 0.0,
        "mrr": reciprocal / total if total else 0.0,
    }


def _render(result: dict, top_k: int) -> str:
    """Render a Markdown baseline report."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Retrieval Baseline (Offline)",
        "",
        f"Recorded {stamp}. **Offline mode: fake embeddings, SQLite, substring matching.**",
        "",
        "> [!NOTE]",
        "> This baseline measures plumbing correctness, not retrieval quality.",
        "> Fake embeddings produce hash vectors with no semantic meaning.",
        "> A quality baseline requires PostgreSQL with real embeddings (`run_eval.py`).",
        "",
        "## Pinned Configuration",
        "",
        "| Setting | Value |",
        "|---|---|",
        "| Embedding model | `fake-deterministic` |",
        f"| Embedding dimensions | {settings.gemini_embedding_dimensions} |",
        f"| Chunk size / overlap | {settings.chunk_size} / {settings.chunk_overlap} |",
        "| Corpus | Phase 4 seed catalog (20 synthetic datasheets) |",
        "| Question set | docs/eval/questions.json |",
        f"| top_k | {top_k} |",
        "",
        "## Results",
        "",
        f"| Configuration | Questions | hit@1 | hit@5 | hit@{top_k} | MRR |",
        f"|---|---|---|---|---|---|",
        f"| {result['mode']} | {result['questions']} | "
        f"{result['hit@1']:.2f} | {result['hit@5']:.2f} | {result[f'hit@{top_k}']:.2f} | "
        f"{result['mrr']:.3f} |",
        "",
        "## Label Verification",
        "",
        f"- **Labels verified** (correct passage exists in corpus): {result['labels_verified']}",
        f"- **Labels unverified** (expected passage not found): {result['labels_unverified']}",
        f"- **Negative questions** (no expected document, skipped): {result['negative_skipped']}",
        "",
        "## Interpretation",
        "",
        "- Hash-based fake vectors have **no semantic relationship** to text content.",
        "  Any non-zero hit rate comes from lucky hash collisions, not retrieval quality.",
        "- The purpose of this baseline is to validate the evaluation pipeline,",
        "  question labels, and scoring logic work end-to-end.",
        "- **Label verification** confirms that every labeled question has a matching",
        "  passage somewhere in the seeded corpus. A label-verified count below the",
        "  total signals a labeling error or a missing seed document.",
        "- The quality target is set **after** running `run_eval.py` against PostgreSQL",
        "  with real Gemini embeddings, not before.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline retrieval evaluation")
    parser.add_argument(
        "--questions",
        type=Path,
        default=ROOT / "docs" / "eval" / "questions.json",
    )
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    print("Setting up in-memory SQLite database...")
    db, org, ws = _setup_db()

    print("Seeding Phase 4 catalog documents and chunks...")
    n = _seed_catalog(db, org, ws)
    print(f"  Seeded {n} documents with chunks")

    print(f"Loading questions from {args.questions}...")
    questions = _load_questions(db, args.questions)
    print(f"  Loaded {len(questions)} questions")

    print("Fetching all chunks...")
    all_chunks = _get_chunks(db)
    print(f"  Found {len(all_chunks)} chunks")

    print("Running offline evaluation (fake cosine scoring)...")
    result = _evaluate_offline(questions, all_chunks, top_k=args.top_k)

    report = _render(result, args.top_k)
    print()
    print(report)

    if args.out:
        args.out.write_text(report, encoding="utf-8")
        print(f"Written to {args.out}")


if __name__ == "__main__":
    main()
