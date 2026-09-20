from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import ask, auth, catalog, documents, health, jobs, search, workflows
from app.core.config import settings
from app.core.logging import setup_logging
from app.jobs.worker import start_background_workers, stop_background_workers
from app.workflows.worker import start_workflow_workers, stop_workflow_workers

setup_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    start_background_workers()
    start_workflow_workers()
    try:
        yield
    finally:
        stop_workflow_workers()
        stop_background_workers()


app = FastAPI(
    title="Solution Engineering Knowledge Workspace",
    version="0.7.0",
    description=(
        "Phase 1 (ingestion), Phase 2 (hybrid retrieval), Phase 3 (grounded answers), "
        "Phase 4 (product catalog & typed graph), Phase 0 (JWT, PostgreSQL RLS, audit), "
        "Phase 5 (tool calling, durable workflow runner, HITL), Phase 6 (RFP responder), "
        "Phase 7 (workflow workspace UI)."
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


@app.get("/", tags=["health"])
def root() -> dict:
    return {
        "name": "Solution Engineering Knowledge Workspace",
        "version": "0.7.0",
        "phases_implemented": [
            "0 - JWT auth, PostgreSQL RLS, audit log",
            "1 - ingestion",
            "2 - hybrid retrieval",
            "3 - grounded answers & conversations",
            "4 - product catalog & typed graph",
            "5 - tool calling, durable workflows, HITL",
            "6 - RFP responder playbook",
            "7 - workflow workspace UI",
        ],
        "phase_0_status": "done",
        "docs": "/docs",
    }

