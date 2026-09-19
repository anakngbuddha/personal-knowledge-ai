from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import documents, health, jobs, search
from app.core.config import settings
from app.core.logging import setup_logging
from app.jobs.worker import start_background_workers, stop_background_workers

setup_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    start_background_workers()
    try:
        yield
    finally:
        stop_background_workers()


app = FastAPI(
    title="Solution Engineering Knowledge Workspace",
    version="0.2.0",
    description=(
        "Phase 1 (ingestion) and Phase 2 (hybrid retrieval) of Project_Plan.md. "
        "Phase 0 (authentication, RLS, audit log) is not built: see docs/PHASE1-2.md."
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
app.include_router(documents.router)
app.include_router(search.router)
app.include_router(jobs.router)


@app.get("/", tags=["health"])
def root() -> dict:
    return {
        "name": "Solution Engineering Knowledge Workspace",
        "version": "0.2.0",
        "phases_implemented": ["1 - ingestion", "2 - hybrid retrieval"],
        "phase_0_status": "partial: data model and enforcement seam only, no authN/RLS",
        "docs": "/docs",
    }
