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
    """Phase 0 exit check: can the backend reach PostgreSQL, pgvector, R2, and Gemini?"""
    checks: dict[str, dict] = {}

    try:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
            has_vector = conn.execute(
                text("select count(*) from pg_extension where extname = 'vector'")
            ).scalar_one()
        checks["postgres"] = {"ok": True, "pgvector": bool(has_vector)}
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

    return {"ok": all(check.get("ok") for check in checks.values()), "checks": checks}
