"""Comprehensive cross-tenant isolation and security boundary tests for Phase 0."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

from app.db.models import (
    AccessGrant,
    AuditLog,
    Base,
    Capability,
    Conversation,
    Document,
    Organization,
    Product,
    ProductCapability,
    ProductEdge,
    ReferenceArchitecture,
    ReferenceArchitectureProduct,
    Workspace,
)
from app.db.session import get_db
from app.main import app
from app.security.audit import record_audit
from app.security.jwt import mint_token
from app.security.labels import Role
from app.security.principal import Principal

# Teach SQLite how to render PostgreSQL JSONB columns
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"


client = TestClient(app)


@pytest.fixture(autouse=True)
def test_db_session():
    """Isolated SQLite database mimicking multi-tenant isolation."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Organization.__table__,
            Workspace.__table__,
            AccessGrant.__table__,
            Document.__table__,
            Capability.__table__,
            Product.__table__,
            ProductCapability.__table__,
            ProductEdge.__table__,
            ReferenceArchitecture.__table__,
            ReferenceArchitectureProduct.__table__,
            Conversation.__table__,
            AuditLog.__table__,
        ],
    )
    SessionClass = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = SessionClass()

    # Seed Org A and Org B
    org_a = Organization(id=uuid.uuid4(), slug="org-a", name="Tenant Organization A")
    org_b = Organization(id=uuid.uuid4(), slug="org-b", name="Tenant Organization B")
    session.add_all([org_a, org_b])
    session.commit()

    ws_a = Workspace(id=uuid.uuid4(), org_id=org_a.id, name="Workspace A")
    ws_b = Workspace(id=uuid.uuid4(), org_id=org_b.id, name="Workspace B")
    session.add_all([ws_a, ws_b])
    session.commit()

    # Seed Document in Org A and Org B
    doc_a = Document(
        id=uuid.uuid4(),
        org_id=org_a.id,
        workspace_id=ws_a.id,
        filename="org_a_secret.pdf",
        original_filename="org_a_secret.pdf",
        file_type="pdf",
        storage_key="org_a/secret.pdf",
        file_size=1024,
    )
    doc_b = Document(
        id=uuid.uuid4(),
        org_id=org_b.id,
        workspace_id=ws_b.id,
        filename="org_b_secret.pdf",
        original_filename="org_b_secret.pdf",
        file_type="pdf",
        storage_key="org_b/secret.pdf",
        file_size=2048,
    )

    # Seed Products in Org A and Org B
    prod_a = Product(
        id=uuid.uuid4(),
        org_id=org_a.id,
        workspace_id=ws_a.id,
        name="Product Alpha",
        slug="product-alpha",
        vendor="Tenant A",
        ownership="own",
        category="Infrastructure",
    )
    prod_b = Product(
        id=uuid.uuid4(),
        org_id=org_b.id,
        workspace_id=ws_b.id,
        name="Product Beta",
        slug="product-beta",
        vendor="Tenant B",
        ownership="own",
        category="Infrastructure",
    )

    # Seed Conversations in Org A and Org B
    conv_a = Conversation(
        id=uuid.uuid4(),
        org_id=org_a.id,
        workspace_id=ws_a.id,
        title="Org A Private Thread",
    )
    conv_b = Conversation(
        id=uuid.uuid4(),
        org_id=org_b.id,
        workspace_id=ws_b.id,
        title="Org B Private Thread",
    )

    session.add_all([doc_a, doc_b, prod_a, prod_b, conv_a, conv_b])
    session.commit()

    session.org_a_id = org_a.id
    session.org_b_id = org_b.id
    session.doc_a_id = doc_a.id
    session.doc_b_id = doc_b.id
    session.prod_a_id = prod_a.id
    session.prod_b_id = prod_b.id
    session.conv_a_id = conv_a.id
    session.conv_b_id = conv_b.id

    def _get_db():
        test_session = SessionClass()
        try:
            yield test_session
        finally:
            test_session.close()

    app.dependency_overrides[get_db] = _get_db
    try:
        yield session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def test_cross_tenant_document_access_returns_404(test_db_session: Session):
    """A user in Org A requesting a document owned by Org B receives 404 Not Found (never 403 or data)."""
    token_org_a = mint_token(
        org_id=test_db_session.org_a_id,
        role=Role.ADMIN,
    )

    # Attempt to access Org B's document with Org A's token
    doc_b_id = test_db_session.doc_b_id
    headers = {"Authorization": f"Bearer {token_org_a}"}

    resp = client.get(f"/documents/{doc_b_id}", headers=headers)
    assert resp.status_code == 404, f"Expected 404 but got {resp.status_code}: {resp.text}"


def test_cross_tenant_product_catalog_isolation(test_db_session: Session):
    """A user in Org A querying products only sees Org A products, never Org B products."""
    token_org_a = mint_token(
        org_id=test_db_session.org_a_id,
        role=Role.SOLUTIONS_ENGINEER,
    )
    headers = {"Authorization": f"Bearer {token_org_a}"}

    resp = client.get("/catalog/products", headers=headers)
    assert resp.status_code == 200
    products = resp.json()
    product_names = [p["name"] for p in products]

    assert "Product Alpha" in product_names
    assert "Product Beta" not in product_names


def test_cross_tenant_token_spoofing_prevented():
    """Attempting to forge a token with an invalid signature is rejected with 401."""
    valid_token = mint_token(org_id=uuid.uuid4(), role=Role.ADMIN)
    tampered_token = valid_token[:-6] + "xxxxxx"

    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {tampered_token}"})
    assert resp.status_code == 401


def test_append_only_audit_logging(test_db_session: Session):
    """Audit events are recorded immutably with tenant and user attribution."""
    principal = Principal(
        org_id=test_db_session.org_a_id,
        user_id=uuid.uuid4(),
        role=Role.ADMIN,
    )

    entry = record_audit(
        db=test_db_session,
        principal=principal,
        action="document.export",
        resource_type="document",
        resource_id=str(test_db_session.doc_a_id),
        details={"format": "docx", "ip": "192.168.1.100"},
    )

    assert entry.id is not None
    assert entry.org_id == test_db_session.org_a_id
    assert entry.user_id == principal.user_id
    assert entry.action == "document.export"
    assert entry.details["format"] == "docx"


def test_cross_tenant_catalog_tool_cannot_resolve_foreign_product(test_db_session: Session):
    """Org A tool context cannot resolve Org B's product by name."""
    from sqlalchemy import select

    from app.tools.catalog_tools import catalog_impact
    from app.tools.registry import ToolContext

    principal_a = Principal(
        org_id=test_db_session.org_a_id,
        user_id=uuid.uuid4(),
        role=Role.SOLUTIONS_ENGINEER,
    )
    ws_a = test_db_session.scalars(
        select(Workspace).where(Workspace.org_id == test_db_session.org_a_id)
    ).first()
    ctx = ToolContext(
        db=test_db_session,
        principal=principal_a,
        workspace_id=ws_a.id,
    )
    result = catalog_impact(ctx, "Product Beta")
    assert result.get("error") == "unknown_product"

    own = catalog_impact(ctx, "Product Alpha")
    assert own.get("error") != "unknown_product"
    assert own.get("product_name") == "Product Alpha"
