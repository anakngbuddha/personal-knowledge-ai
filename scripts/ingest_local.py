"""Ingest a local file through the real pipeline without going through HTTP.

    cd backend && python ../scripts/ingest_local.py ~/Downloads/lecture03.pdf
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db.session import SessionLocal  # noqa: E402
from app.documents.service import create_document, process_document  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: python ingest_local.py <path-to-file>")
    path = Path(sys.argv[1]).expanduser()
    data = path.read_bytes()

    db = SessionLocal()
    try:
        document = create_document(
            db, original_filename=path.name, data=data, mime_type=None
        )
        print(f"created document {document.id}")
    finally:
        db.close()

    process_document(document.id)

    db = SessionLocal()
    try:
        from app.db.models import Document

        refreshed = db.get(Document, document.id)
        print(f"status={refreshed.status} chunks={refreshed.chunk_count} error={refreshed.error_message}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
