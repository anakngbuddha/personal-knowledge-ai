from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    agent_actions,
    advisor,
    ask,
    auth,
    catalog,
    catalog_import,
    documents,
    freshness,
    graph_review,
    health,
    integrations,
    jobs,
    map_edit,
    mcp_server,
    notebooks,
    notes,
    ops,
    phase8,
    runtime,
    search,
    studio,
    workflows,
)
from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.db.bootstrap import ensure_schema, should_bootstrap
from app.freshness.worker import start_freshness_workers, stop_freshness_workers
from app.jobs.worker import start_background_workers, stop_background_workers
from app.mcp.supervisor import start_supervisor, stop_supervisor
from app.ops.runtime_metrics import start_runtime_metrics, stop_runtime_metrics
from app.workflows.worker import start_workflow_workers, stop_workflow_workers

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if should_bootstrap():
        ensure_schema()
    # Audit finding 4: verify the DB role cannot bypass row-level security.
    try:
        from app.db.rls import check_rls_posture
        from app.db.session import engine

        check_rls_posture(engine, required=settings.rls_required)
    except RuntimeError:
        raise
    except Exception:  # noqa: BLE001 - an unreachable DB is reported by /health
        logger.warning("could not check RLS posture", exc_info=True)
    # Render restarts leave RUNNING jobs locked; reclaim them before workers start.
    try:
        from app.db.session import system_session
        from app.jobs import queue as job_queue

        db = system_session()
        try:
            job_queue.reap_stale(db)
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        pass
    start_background_workers()
    start_workflow_workers()
    start_freshness_workers()
    start_supervisor()
    start_runtime_metrics()
    try:
        yield
    finally:
        await stop_runtime_metrics()
        stop_supervisor()
        stop_freshness_workers()
        stop_workflow_workers()
        stop_background_workers()


app = FastAPI(
    title="Solution Engineering Knowledge Workspace",
    version="1.1.0",
    description=(
        "Solution engineering workspace: ingestion, hybrid retrieval, grounded answers, product graph, "
        "durable workflows with human approval, RFP playbooks, advisor, notes and notebooks, vendor "
        "freshness, SSO, and an MCP server/client. See files/STATUS.md for the endpoint-backed "
        "capability inventory (implemented / partial / proposed)."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(search.router)
app.include_router(studio.router)
app.include_router(jobs.router)
app.include_router(ask.router)
app.include_router(agent_actions.router)
app.include_router(catalog_import.router)
app.include_router(catalog.router)
app.include_router(map_edit.router)
app.include_router(graph_review.router)
app.include_router(workflows.router)
app.include_router(phase8.router)
app.include_router(advisor.router)
app.include_router(integrations.router)
app.include_router(mcp_server.router)
app.include_router(notebooks.router)
app.include_router(notes.router)
app.include_router(freshness.router)
app.include_router(ops.router)
app.include_router(runtime.router)


@app.get("/", tags=["health"])
def root() -> dict:
    return {
        "name": "Solution Engineering Knowledge Workspace",
        "version": "1.1.0",
        "capabilities": "files/STATUS.md",
        "docs": "/docs",
    }
