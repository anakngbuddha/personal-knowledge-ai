"""Retrieval evaluation: vector-only vs keyword-only vs hybrid + RRF.

    cd backend && python ../scripts/run_eval.py --out ../docs/retrieval-baseline.md

Project_Plan.md Phase 2 requires a **written baseline recorded before tuning**, and
section 5 adds two standing rules: pin prompts and models during a comparison, and
record the baseline before tuning or improvement cannot be distinguished from noise.
So this script prints the pinned model, embedding dimensions, chunking parameters and
RRF k alongside every number. A result without its configuration is not a baseline.

Metrics: hit@1, hit@5, hit@k and MRR against the labeled set. A hit means the correct
passage appears in the returned chunks, matched by `expected_text_contains` when the
label has one and by document id otherwise.
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.models import EvaluationQuestion  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.retrieval.search import search  # noqa: E402
from app.security.deps import get_or_create_default_org  # noqa: E402
from app.security.principal import owner_principal  # noqa: E402

MODES = ("vector", "keyword", "hybrid")


def is_hit(question: EvaluationQuestion, hit) -> bool:
    if question.expected_text_contains:
        needle = " ".join(question.expected_text_contains.lower().split())
        haystack = " ".join(hit.text.lower().split())
        if needle in haystack:
            return True
        # A label may point at a passage that landed in a neighbouring chunk of the
        # right document and page; that still counts as retrieving the right evidence.
        if question.expected_document_id and str(question.expected_document_id) == hit.document_id:
            if question.expected_page_number and hit.page_number == question.expected_page_number:
                return True
        return False
    if question.expected_document_id:
        return str(question.expected_document_id) == hit.document_id
    return False


def evaluate(db, principal, questions, mode: str, top_k: int) -> dict:
    hits_at = {1: 0, 5: 0, top_k: 0}
    reciprocal = 0.0
    unlabeled = 0
    latencies: list[float] = []

    for question in questions:
        if not (question.expected_text_contains or question.expected_document_id):
            unlabeled += 1
            continue
        result = search(
            db,
            principal=principal,
            query=question.question,
            mode=mode,  # type: ignore[arg-type]
            top_k=top_k,
        )
        latencies.append(result.timings_ms.get("total_ms", 0.0))
        rank = next(
            (i for i, hit in enumerate(result.hits, start=1) if is_hit(question, hit)),
            None,
        )
        if rank:
            reciprocal += 1.0 / rank
            for cutoff in hits_at:
                if rank <= cutoff:
                    hits_at[cutoff] += 1

    total = len(questions) - unlabeled
    latencies.sort()

    def percentile(p: float) -> float:
        if not latencies:
            return 0.0
        index = min(len(latencies) - 1, int(round(p * (len(latencies) - 1))))
        return latencies[index]

    return {
        "mode": mode,
        "questions": total,
        "unlabeled_skipped": unlabeled,
        "hit@1": hits_at[1] / total if total else 0.0,
        "hit@5": hits_at[5] / total if total else 0.0,
        f"hit@{top_k}": hits_at[top_k] / total if total else 0.0,
        "mrr": reciprocal / total if total else 0.0,
        "p50_ms": round(percentile(0.50), 1),
        "p95_ms": round(percentile(0.95), 1),
    }


def render(rows: list[dict], top_k: int) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Retrieval baseline",
        "",
        f"Recorded {stamp}. **Do not tune before this table exists.**",
        "",
        "## Pinned configuration",
        "",
        "| Setting | Value |",
        "|---|---|",
        f"| Embedding model | `{settings.gemini_embedding_model}` |",
        f"| Embedding dimensions | {settings.gemini_embedding_dimensions} |",
        f"| Embedding provider | `{settings.embedding_provider}` |",
        f"| Chunk size / overlap | {settings.chunk_size} / {settings.chunk_overlap} |",
        f"| FTS configuration | `{settings.fts_config}` |",
        f"| RRF k | {settings.rrf_k} |",
        f"| Candidates per branch | {settings.candidate_k} |",
        f"| top_k | {top_k} |",
        "",
        "## Results",
        "",
        f"| Configuration | Questions | hit@1 | hit@5 | hit@{top_k} | MRR | p50 | p95 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    labels = {"vector": "A - vector only", "keyword": "B - keyword only", "hybrid": "C - hybrid + RRF"}
    for row in rows:
        lines.append(
            f"| {labels.get(row['mode'], row['mode'])} | {row['questions']} | "
            f"{row['hit@1']:.2f} | {row['hit@5']:.2f} | {row[f'hit@{top_k}']:.2f} | "
            f"{row['mrr']:.3f} | {row['p50_ms']:.0f} ms | {row['p95_ms']:.0f} ms |"
        )
    lines += [
        "",
        "## Latency budget",
        "",
        "Phase 2 sets p95 under 500 ms and expects it to be met trivially at this corpus",
        "size. It is recorded as a regression tripwire, not as an achievement.",
        "",
        "## Notes",
        "",
        "- `EMBEDDING_PROVIDER=fake` produces hash vectors with no semantic meaning. A",
        "  baseline run with the fake provider measures plumbing, not retrieval quality;",
        "  the vector column will look random and that is correct.",
        "- The quality target is chosen *after* this table exists, not before.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-k", type=int, default=settings.top_k)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        principal = owner_principal(get_or_create_default_org(db).id)
        questions = list(db.scalars(select(EvaluationQuestion).order_by(EvaluationQuestion.created_at)))
        if not questions:
            raise SystemExit(
                "no labeled questions. Run seed_eval_set.py with docs/eval/questions.json first."
            )
        rows = [evaluate(db, principal, questions, mode, args.top_k) for mode in MODES]
    finally:
        db.close()

    report = render(rows, args.top_k)
    print(report)
    if args.out:
        args.out.write_text(report, encoding="utf-8")
        print(f"\nwritten to {args.out}")


if __name__ == "__main__":
    main()
