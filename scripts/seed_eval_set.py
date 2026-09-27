"""Load the labeled retrieval question set into `evaluation_questions`.

    cd backend && python ../scripts/seed_eval_set.py ../docs/eval/questions.json

The label is `expected_text_contains` first and `expected_document_id` second, not a
chunk id. Chunk ids change every time chunking changes, and a labeled set that dies on
a chunking tweak is a labeled set nobody maintains. A substring of the correct passage
survives re-chunking, which is the property that matters.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import select  # noqa: E402

from app.db.models import Document, EvaluationQuestion  # noqa: E402
from app.db.session import system_session  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: python seed_eval_set.py <questions.json>")
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    questions = payload["questions"] if isinstance(payload, dict) else payload

    db = system_session()
    try:
        by_filename = {
            document.original_filename: document
            for document in db.scalars(select(Document).where(Document.is_current.is_(True)))
        }

        db.query(EvaluationQuestion).delete()
        loaded = 0
        unresolved: list[str] = []
        for item in questions:
            filename = item.get("document_filename")
            document = by_filename.get(filename) if filename else None
            if filename and document is None:
                unresolved.append(filename)
            db.add(
                EvaluationQuestion(
                    question=item["question"],
                    expected_document_id=document.id if document else None,
                    expected_page_number=item.get("page_number"),
                    expected_text_contains=item.get("text_contains"),
                    tags=item.get("tags"),
                    notes=item.get("notes"),
                )
            )
            loaded += 1
        db.commit()
    finally:
        db.close()

    print(f"loaded {loaded} question(s)")
    if unresolved:
        print(
            "WARNING: these documents are not ingested yet, so their questions have no "
            "document label: " + ", ".join(sorted(set(unresolved)))
        )


if __name__ == "__main__":
    main()
