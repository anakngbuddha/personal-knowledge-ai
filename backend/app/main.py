from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import documents, health
from app.core.config import settings
from app.core.logging import setup_logging

setup_logging()

app = FastAPI(
    title="Personal Knowledge AI Workspace",
    version="0.1.0",
    description="V1 backend. Phase 1: document ingestion.",
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


@app.get("/", tags=["health"])
def root() -> dict:
    return {
        "name": "Personal Knowledge AI Workspace",
        "version": "0.1.0",
        "phase": "1 - document ingestion",
        "docs": "/docs",
    }
