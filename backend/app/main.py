from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import ask, auth, catalog, documents, health, jobs, phase8, search, workflows
from app.core.config import settings
from app.core.logging import setup_logging
from app.db.bootstrap import ensure_schema, should_bootstrap
from app.jobs.worker import start_background_workers, stop_background_workers
from app.workflows.worker import start_workflow_workers, stop_workflow_workers

setup_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if should_bootstrap():
        ensure_schema()
    start_background_workers()
    start_workflow_workers()
    try:
        yield
    finally:
        stop_workflow_workers()
        stop_background_workers()


app = FastAPI(
    title="Solution Engineering Knowledge Workspace",
    version="0.8.0",
    description=(
        "Enterprise solution engineering workspace with ingestion, hybrid retrieval, grounded answers, "
        "typed product graph, durable HITL workflows, RFP response, workflow cockpit, and Phase 8 "
        "solution composition and post-sales playbooks."
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
app.include_router(catalog.router)
app.include_router(workflows.router)
app.include_router(phase8.router)


@app.get("/", tags=["health"])
def root() -> dict:
    return {
        "name": "Solution Engineering Knowledge Workspace",
        "version": "0.8.0",
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
        ],
        "phase_0_status": "done",
        "docs": "/docs",
    }
