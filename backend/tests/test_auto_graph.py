"""Auto-graph proposes selling relationships from the product list."""

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.catalog.auto_graph import suggest_solution_graph
from unittest.mock import MagicMock

from app.api.routes import catalog as catalog_routes
from app.core.config import settings
from app.core.errors import ProviderError, ProviderRateLimited
from app.db.models import (
    Base,
    Capability,
    CurationStatus,
    EdgeStatus,
    Organization,
    Product,
    ProductCapability,
    ProductContextLink,
    ProductEdge,
    SellingContext,
    Workspace,
)
from app.db.session import get_db
from app.llm.base import GroundedAnswer
from app.main import app


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"


class _ScriptedLLM:
    def __init__(self, payload: dict | None):
        self.payload = payload
        self.calls = 0

    @property
    def model_id(self) -> str:
        return "scripted"

    def generate_grounded_answer(self, question, context_chunks, *, system_prompt, **kwargs):
        self.calls += 1
        text = "" if self.payload is None else json.dumps(self.payload)
        return GroundedAnswer(text=text, citations=[], model_id=self.model_id, prompt_version="test")


@pytest.fixture
def graph_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Organization.__table__,
            Workspace.__table__,
            Product.__table__,
            Capability.__table__,
            ProductCapability.__table__,
            ProductEdge.__table__,
            SellingContext.__table__,
            ProductContextLink.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    org = Organization(id=uuid.uuid4(), slug=f"org-{uuid.uuid4().hex[:6]}", name="Org")
    session.add(org)
    session.commit()
    ws = Workspace(id=uuid.uuid4(), org_id=org.id, name="Desk")
    other = Workspace(id=uuid.uuid4(), org_id=org.id, name="Other")
    session.add_all([ws, other])
    session.commit()
    session.org_id = org.id
    session.workspace_id = ws.id
    session.other_workspace_id = other.id
    try:
        yield session
    finally:
        session.close()


def _product(session, name: str, *, workspace_id=None, curation=CurationStatus.CONFIRMED) -> Product:
    row = Product(
        org_id=session.org_id,
        workspace_id=workspace_id or session.workspace_id,
        name=name,
        slug=name.lower().replace(" ", "-") + uuid.uuid4().hex[:4],
        vendor="Acme",
        ownership="own",
        category="Audio",
        description=f"{name} for meeting rooms",
        curation_status=curation,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _proposal(source: str, target: str) -> dict:
    return {
        "edges": [
            {
                "source": source,
                "target": target,
                "relation_type": "bundles_with",
                "evidence": f"{source} is sold with {target} for a complete room.",
                "confidence": 0.7,
            }
        ],
        "contexts": [
            {
                "product": source,
                "kind": "use_case",
                "name": "Huddle rooms",
                "relation_type": "suits_use_case",
                "evidence": f"{source} suits small huddle rooms.",
                "confidence": 0.9,
            }
        ],
    }


def test_auto_graph_files_bundle_and_use_case(graph_db):
    speaker = _product(graph_db, "Speak 750")
    bar = _product(graph_db, "Video Bar")
    llm = _ScriptedLLM(_proposal(speaker.name, bar.name))
    result = suggest_solution_graph(
        graph_db, workspace_id=graph_db.workspace_id, org_id=graph_db.org_id, provider=llm
    )
    assert llm.calls == 1
    assert len(result.edges) == 1
    assert result.edges[0].relation_type == "bundles_with"
    assert result.edges[0].status == EdgeStatus.PENDING_REVIEW
    assert result.edges[0].is_ai_suggested is True
    assert len(result.context_links) == 1
    assert result.context_links[0].status == EdgeStatus.APPROVED
    assert result.context_links[0].confidence >= settings.graph_auto_accept_confidence


def test_auto_graph_skips_existing_and_rejected(graph_db):
    speaker = _product(graph_db, "Speak 750")
    bar = _product(graph_db, "Video Bar")
    graph_db.add(
        ProductEdge(
            org_id=graph_db.org_id,
            workspace_id=graph_db.workspace_id,
            source_product_id=speaker.id,
            target_product_id=bar.id,
            relation_type="bundles_with",
            evidence="Already reviewed.",
            confidence=1.0,
            status=EdgeStatus.REJECTED,
            is_ai_suggested=True,
        )
    )
    graph_db.commit()
    llm = _ScriptedLLM(_proposal(speaker.name, bar.name))
    result = suggest_solution_graph(
        graph_db, workspace_id=graph_db.workspace_id, org_id=graph_db.org_id, provider=llm
    )
    assert result.edges == []
    assert len(result.context_links) == 1
    again = suggest_solution_graph(
        graph_db, workspace_id=graph_db.workspace_id, org_id=graph_db.org_id, provider=llm
    )
    assert again.context_links == []
    stored = list(graph_db.scalars(select(ProductEdge)).all())
    assert len(stored) == 1
    assert stored[0].status == EdgeStatus.REJECTED


def test_single_product_does_not_call_the_model(graph_db):
    _product(graph_db, "Speak 750")
    llm = _ScriptedLLM(_proposal("Speak 750", "Video Bar"))
    result = suggest_solution_graph(
        graph_db, workspace_id=graph_db.workspace_id, org_id=graph_db.org_id, provider=llm
    )
    assert result.proposed == 0
    assert llm.calls == 0


def test_other_workspace_products_are_ignored(graph_db):
    _product(graph_db, "Speak 750", workspace_id=graph_db.other_workspace_id)
    _product(graph_db, "Video Bar", workspace_id=graph_db.other_workspace_id)
    llm = _ScriptedLLM(_proposal("Speak 750", "Video Bar"))
    result = suggest_solution_graph(
        graph_db, workspace_id=graph_db.workspace_id, org_id=graph_db.org_id, provider=llm
    )
    assert result.proposed == 0
    assert llm.calls == 0
    assert list(graph_db.scalars(select(ProductEdge)).all()) == []


def test_auto_graph_route_requires_auth(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "jwt")
    monkeypatch.setattr(settings, "environment", "development")
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[Organization.__table__])
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(Organization(slug=settings.default_org_slug, name="Default"))
    session.commit()

    def _get_test_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_test_db
    try:
        client = TestClient(app)
        response = client.post("/graph/auto-graph")
        assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def test_auto_graph_route_maps_provider_failures():
    def _db():
        yield MagicMock()

    def _deps():
        return MagicMock(), uuid.uuid4(), uuid.uuid4()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[catalog_routes._get_service] = _deps
    try:
        client = TestClient(app)

        def _limited(*_args, **_kwargs):
            raise ProviderRateLimited("Gemini generation rate limit reached")

        catalog_routes.suggest_solution_graph = _limited
        limited = client.post("/graph/auto-graph")
        assert limited.status_code == 429
        assert limited.json()["detail"] == "The model is busy. Wait a moment and try Auto-graph again."

        def _down(*_args, **_kwargs):
            raise ProviderError("model down")

        catalog_routes.suggest_solution_graph = _down
        down = client.post("/graph/auto-graph")
        assert down.status_code == 503
        assert "could not graph" in down.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(catalog_routes._get_service, None)
        catalog_routes.suggest_solution_graph = suggest_solution_graph
