from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
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
    notes,
    ops,
    phase8,
    search,
    workflows,
)
from app.core.config import settings
from app.core.logging import setup_logging
from app.db.bootstrap import ensure_schema, should_bootstrap
from app.freshness.worker import start_freshness_workers, stop_freshness_workers
from app.jobs.worker import start_background_workers, stop_background_workers
from app.mcp.supervisor import start_supervisor, stop_supervisor
from app.workflows.worker import start_workflow_workers, stop_workflow_workers

setup_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if should_bootstrap():
        ensure_schema()
    start_background_workers()
    start_workflow_workers()
    start_freshness_workers()
    start_supervisor()
    try:
        yield
    finally:
        stop_supervisor()
        stop_freshness_workers()
        stop_workflow_workers()
        stop_background_workers()


app = FastAPI(
    title="Solution Engineering Knowledge Workspace",
    version="1.0.0",
    description=(
        "Enterprise solution engineering workspace with ingestion, hybrid retrieval, grounded answers, "
        "typed product graph, durable HITL workflows, RFP response, workflow cockpit, Phase 8 "
        "solution composition, Phase 9 MCP integrations, and Phase 10 notes, freshness, SSO, and restore drills."
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
app.include_router(jobs.router)
app.include_router(ask.router)
app.include_router(catalog_import.router)
app.include_router(catalog.router)
app.include_router(graph_review.router)
app.include_router(workflows.router)
app.include_router(phase8.router)
app.include_router(integrations.router)
app.include_router(notes.router)
app.include_router(freshness.router)
app.include_router(ops.router)


@app.get("/", tags=["health"])
def root() -> dict:
    return {
        "name": "Solution Engineering Knowledge Workspace",
        "version": "1.0.0",
        "phases_implemented": [
            "0 - JWT auth, PostgreSQL RLS, audit log",
            "1 - ingestion",
            "2 - hybrid retrieval",
            "3 - grounded answers & conversations",
            "4 - product catalog & typed graph",
            "5 - tool calling, durable workflows, HITL",
            "6 - RFP responder playbook",
            "7 - workflow workspace UI",
            "8 - solution composer, incident triage, upgrade impact audit",
            "9 - MCP client (Playwright, Microsoft 365, Brave Search)",
            "10 - tribal notes, vendor freshness, SSO, restore drills",
        ],
        "phase_0_status": "done",
        "docs": "/docs",
    }
