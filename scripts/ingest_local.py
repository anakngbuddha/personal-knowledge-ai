"""Ingest local files through the real pipeline without going through HTTP.

    cd backend && python ../scripts/ingest_local.py ~/collateral/*.pdf

Useful for building the Phase 2 baseline corpus, and it exercises exactly the code the
API exercises: sniffing, scanning, dedup, versioning, extraction, chunking, embedding.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.errors import DuplicateDocument  # noqa: E402
from app.db.models import Document  # noqa: E402
from app.db.session import system_session  # noqa: E402
from app.documents.metadata import DocumentMetadataIn  # noqa: E402
from app.documents.service import create_document, process_document  # noqa: E402
from app.security.deps import get_or_create_default_org  # noqa: E402
from app.security.principal import owner_principal  # noqa: E402


def main() -> None:
    paths = [Path(arg).expanduser() for arg in sys.argv[1:]]
    if not paths:
        raise SystemExit("usage: python ingest_local.py <file> [file ...]")

    db = system_session()
    try:
        principal = owner_principal(get_or_create_default_org(db).id)
        queued: list[Document] = []
        for path in paths:
            try:
                document = create_document(
                    db,
                    principal=principal,
                    original_filename=path.name,
                    data=path.read_bytes(),
                    metadata=DocumentMetadataIn(),
                )
                queued.append(document)
                print(f"created {document.id}  {path.name}  v{document.version}")
            except DuplicateDocument as exc:
                print(f"skipped {path.name}: {exc}")
            except Exception as exc:  # noqa: BLE001
                print(f"failed  {path.name}: {type(exc).__name__}: {exc}")
    finally:
        db.close()

    for document in queued:
        try:
            process_document(document.id)
        except Exception as exc:  # noqa: BLE001
            print(f"processing failed for {document.id}: {type(exc).__name__}: {exc}")

    db = system_session()
    try:
        for document in queued:
            row = db.get(Document, document.id)
            print(
                f"{row.original_filename}: status={row.status} chunks={row.chunk_count} "
                f"pages={row.page_count} ocr={row.ocr_applied} "
                f"flags={row.injection_flag_count} error={row.error_message}"
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
