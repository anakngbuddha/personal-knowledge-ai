from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import settings
from app.db.session import engine

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "environment": settings.environment}


@router.get("/health/dependencies")
def dependencies() -> dict:
    """Can the backend reach PostgreSQL, pgvector, object storage, and the embedding
    provider, and are the ingestion safety controls actually on?"""
    checks: dict[str, dict] = {}

    try:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
            has_vector = conn.execute(
                text("select count(*) from pg_extension where extname = 'vector'")
            ).scalar_one()
            fts_ok = conn.execute(
                text("select count(*) from pg_ts_config where cfgname = :name"),
                {"name": settings.fts_config},
            ).scalar_one()
            pending = conn.execute(
                text(
                    "select count(*) from information_schema.columns "
                    "where table_name = 'documents' and column_name = 'content_hash'"
                )
            ).scalar_one()
        checks["postgres"] = {
            "ok": bool(has_vector) and bool(fts_ok) and bool(pending),
            "pgvector": bool(has_vector),
            "fts_config": settings.fts_config,
            "fts_config_present": bool(fts_ok),
            "schema_migrated": bool(pending),
        }
    except Exception as exc:  # noqa: BLE001
        checks["postgres"] = {"ok": False, "error": str(exc)[:300]}

    try:
        from app.storage.factory import get_storage

        storage = get_storage()
        probe_key = "_healthcheck/probe.txt"
        storage.put(probe_key, b"ok", content_type="text/plain")
        storage.delete(probe_key)
        checks["storage"] = {"ok": True, "backend": settings.storage_backend}
    except Exception as exc:  # noqa: BLE001
        checks["storage"] = {"ok": False, "error": str(exc)[:300]}

    try:
        from app.embeddings.factory import get_embedding_provider

        provider = get_embedding_provider()
        vector = provider.embed_query("connectivity check")
        checks["embeddings"] = {
            "ok": len(vector) == provider.dimensions,
            "model": provider.model_id,
            "dimensions": len(vector),
        }
    except Exception as exc:  # noqa: BLE001
        checks["embeddings"] = {"ok": False, "error": str(exc)[:300]}

    # Scanning is a configured control, so a misconfigured scanner is a failed health
    # check rather than a surprise at upload time.
    try:
        from app.documents.scanning import get_scanner

        scanner = get_scanner()
        checks["malware_scanner"] = {
            "ok": scanner.name != "none",
            "backend": scanner.name,
            "note": "scanning disabled" if scanner.name == "none" else None,
        }
    except Exception as exc:  # noqa: BLE001
        checks["malware_scanner"] = {"ok": False, "error": str(exc)[:300]}

    try:
        from app.ocr.factory import get_ocr_provider

        ocr = get_ocr_provider()
        checks["ocr"] = {"ok": True, "provider": ocr.name, "available": ocr.available}
    except Exception as exc:  # noqa: BLE001
        checks["ocr"] = {"ok": False, "error": str(exc)[:300]}

    # LLM / chat key — never return the secret, only whether it is set.
    try:
        provider_name = (settings.llm_provider or "gemini").lower()
        if provider_name == "fake":
            checks["llm"] = {
                "ok": True,
                "provider": "fake",
                "key_configured": True,
                "note": "offline test provider",
            }
        else:
            configured = bool(settings.gemini_api_key)
            checks["llm"] = {
                "ok": configured,
                "provider": provider_name,
                "key_configured": configured,
            }
    except Exception as exc:  # noqa: BLE001
        checks["llm"] = {"ok": False, "error": str(exc)[:300]}

    try:
        from app.db.session import SessionLocal
        from app.jobs import queue

        db = SessionLocal()
        try:
            counts = queue.stats(db)
        finally:
            db.close()
        checks["ingestion_queue"] = {
            "ok": True,
            "counts": counts,
            "worker_in_process": settings.worker_enabled,
        }
    except Exception as exc:  # noqa: BLE001
        checks["ingestion_queue"] = {"ok": False, "error": str(exc)[:300]}

    try:
        from app.llm.limiter import gemini_bucket

        bucket = gemini_bucket()
        checks["gemini"] = {
            "ok": True,
            "queued": bucket.queued,
            "rpm": float(getattr(settings, "gemini_rpm", 10) or 10),
        }
    except Exception as exc:  # noqa: BLE001
        checks["gemini"] = {"ok": False, "error": str(exc)[:300]}

    return {"ok": all(check.get("ok") for check in checks.values()), "checks": checks}
