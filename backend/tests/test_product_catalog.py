"""Phase 4: Product Catalog tests.

Tests product CRUD, slug uniqueness, resold validation,
capability association, and reference architectures.
"""

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker

from app.catalog.models import (
    CapabilityIn,
    ProductCapabilityIn,
    ProductEdgeIn,
    ProductIn,
    ProductUpdate,
    ReferenceArchitectureIn,
    ReferenceArchitectureProductItem,
)
from app.catalog.service import CatalogService
from app.core.errors import AppError
from app.db.models import (
    Base,
    Capability,
    Organization,
    Ownership,
    Product,
    ProductCapability,
    ProductEdge,
    ReferenceArchitecture,
    ReferenceArchitectureProduct,
    Workspace,
)


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"


@pytest.fixture
def catalog_session():
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
            ReferenceArchitecture.__table__,
            ReferenceArchitectureProduct.__table__,
        ],
    )
    SessionClass = sessionmaker(bind=engine)
    session = SessionClass()

    org = Organization(id=uuid.uuid4(), slug=f"test-org-{uuid.uuid4().hex[:8]}", name="Test Org")
    session.add(org)
    session.commit()

    ws = Workspace(id=uuid.uuid4(), org_id=org.id, name="Test Workspace")
    session.add(ws)
    session.commit()

    session.org_id = org.id
    session.workspace_id = ws.id

    try:
        yield session
    finally:
        session.close()


def _make_product(
    session,
    service: CatalogService,
    name: str = "Test Product",
    vendor: str = "TestVendor",
    ownership: str = "own",
    category: str = "Testing",
) -> Product:
    return service.create_product(
        session.org_id,
        session.workspace_id,
        ProductIn(
            name=name,
            vendor=vendor,
            ownership=ownership,
            category=category,
        ),
    )


# ---------------------------------------------------------------------------
# Product CRUD
# ---------------------------------------------------------------------------


class TestProductCRUD:
    def test_create_product_basic(self, catalog_session):
        svc = CatalogService(catalog_session)
        product = _make_product(catalog_session, svc)

        assert product.id is not None
        assert product.name == "Test Product"
        assert product.vendor == "TestVendor"
        assert product.ownership == "own"
        assert product.slug == "test-product"

    def test_create_product_generates_slug(self, catalog_session):
        svc = CatalogService(catalog_session)
        product = svc.create_product(
            catalog_session.org_id,
            catalog_session.workspace_id,
            ProductIn(name="My Fancy Product!", vendor="V", category="Cat"),
        )
        assert product.slug == "my-fancy-product"

    def test_list_products_by_vendor(self, catalog_session):
        svc = CatalogService(catalog_session)
        _make_product(catalog_session, svc, name="P1", vendor="AlphaVendor")
        _make_product(catalog_session, svc, name="P2", vendor="BetaVendor")

        results = svc.list_products(catalog_session.workspace_id, vendor="Alpha")
        assert len(results) == 1
        assert results[0].vendor == "AlphaVendor"

    def test_list_products_by_ownership(self, catalog_session):
        svc = CatalogService(catalog_session)
        _make_product(catalog_session, svc, name="Own1", ownership="own")
        _make_product(catalog_session, svc, name="Resold1", vendor="ExtVendor", ownership="resold")

        own_results = svc.list_products(catalog_session.workspace_id, ownership="own")
        resold_results = svc.list_products(catalog_session.workspace_id, ownership="resold")

        assert any(p.name == "Own1" for p in own_results)
        assert any(p.name == "Resold1" for p in resold_results)

    def test_update_product(self, catalog_session):
        svc = CatalogService(catalog_session)
        product = _make_product(catalog_session, svc)

        updated = svc.update_product(
            product.id,
            catalog_session.workspace_id,
            ProductUpdate(description="Updated description"),
        )
        assert updated is not None
        assert updated.description == "Updated description"

    def test_delete_product(self, catalog_session):
        svc = CatalogService(catalog_session)
        product = _make_product(catalog_session, svc)

        ok = svc.delete_product(product.id, catalog_session.workspace_id)
        assert ok is True

        found = svc.get_product(product.id, catalog_session.workspace_id)
        assert found is None

    def test_get_nonexistent_product_returns_none(self, catalog_session):
        svc = CatalogService(catalog_session)
        found = svc.get_product(uuid.uuid4(), catalog_session.workspace_id)
        assert found is None

    def test_slug_collision_gets_deduplicated(self, catalog_session):
        svc = CatalogService(catalog_session)
        p1 = _make_product(catalog_session, svc, name="Same Name")
        p2 = _make_product(catalog_session, svc, name="Same Name")

        assert p1.slug != p2.slug

    def test_search_products(self, catalog_session):
        svc = CatalogService(catalog_session)
        _make_product(catalog_session, svc, name="Apex Identity Broker")
        _make_product(catalog_session, svc, name="Nova Cloud Storage")

        results = svc.list_products(catalog_session.workspace_id, search="Identity")
        assert len(results) == 1
        assert results[0].name == "Apex Identity Broker"


# ---------------------------------------------------------------------------
# Resold Product Validation
# ---------------------------------------------------------------------------


class TestResoldValidation:
    def test_resold_product_requires_valid_vendor(self, catalog_session):
        svc = CatalogService(catalog_session)
        with pytest.raises(AppError, match="valid third-party vendor"):
            svc.create_product(
                catalog_session.org_id,
                catalog_session.workspace_id,
                ProductIn(name="Bad Resold", vendor="own", ownership="resold", category="Cat"),
            )

    def test_resold_product_with_valid_vendor_succeeds(self, catalog_session):
        svc = CatalogService(catalog_session)
        product = svc.create_product(
            catalog_session.org_id,
            catalog_session.workspace_id,
            ProductIn(
                name="Good Resold",
                vendor="Okta",
                ownership="resold",
                category="Identity",
                partner_tier="Premier",
                support_owner="vendor",
                source_of_truth_url="https://okta.com/products/",
            ),
        )
        assert product.ownership == "resold"
        assert product.vendor == "Okta"
        assert product.partner_tier == "Premier"
        assert product.support_owner == "vendor"


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------


class TestCapabilities:
    def test_create_capability(self, catalog_session):
        svc = CatalogService(catalog_session)
        cap = svc.create_capability(
            catalog_session.org_id,
            CapabilityIn(name="Identity Federation", category="Identity & Access"),
        )
        assert cap.id is not None
        assert cap.slug == "identity-federation"

    def test_duplicate_capability_slug_returns_existing(self, catalog_session):
        svc = CatalogService(catalog_session)
        cap1 = svc.create_capability(
            catalog_session.org_id,
            CapabilityIn(name="Identity Federation", category="Identity & Access"),
        )
        cap2 = svc.create_capability(
            catalog_session.org_id,
            CapabilityIn(name="Identity Federation", category="Identity & Access"),
        )
        assert cap1.id == cap2.id

    def test_assign_capability_to_product(self, catalog_session):
        svc = CatalogService(catalog_session)
        product = _make_product(catalog_session, svc)
        cap = svc.create_capability(
            catalog_session.org_id,
            CapabilityIn(name="SSO", category="Identity"),
        )

        pc = svc.assign_capability_to_product(
            product.id,
            catalog_session.workspace_id,
            ProductCapabilityIn(capability_id=cap.id, proficiency="native"),
        )
        assert pc.proficiency == "native"

    def test_remove_capability_from_product(self, catalog_session):
        svc = CatalogService(catalog_session)
        product = _make_product(catalog_session, svc)
        cap = svc.create_capability(
            catalog_session.org_id,
            CapabilityIn(name="Monitoring", category="Observability"),
        )
        svc.assign_capability_to_product(
            product.id,
            catalog_session.workspace_id,
            ProductCapabilityIn(capability_id=cap.id),
        )

        ok = svc.remove_capability_from_product(product.id, cap.id, catalog_session.workspace_id)
        assert ok is True


# ---------------------------------------------------------------------------
# Reference Architectures
# ---------------------------------------------------------------------------


class TestReferenceArchitectures:
    def test_create_reference_architecture(self, catalog_session):
        svc = CatalogService(catalog_session)
        p1 = _make_product(catalog_session, svc, name="Product A")
        p2 = _make_product(catalog_session, svc, name="Product B")

        arch = svc.create_reference_architecture(
            catalog_session.org_id,
            catalog_session.workspace_id,
            ReferenceArchitectureIn(
                name="Secure Cloud Foundation",
                description="Test architecture",
                products=[
                    ReferenceArchitectureProductItem(product_id=p1.id, role="Identity Provider"),
                    ReferenceArchitectureProductItem(product_id=p2.id, role="Storage Backend"),
                ],
            ),
        )
        assert arch.id is not None
        assert arch.slug == "secure-cloud-foundation"
        assert len(arch.products) == 2

    def test_delete_reference_architecture(self, catalog_session):
        svc = CatalogService(catalog_session)
        p1 = _make_product(catalog_session, svc, name="Product C")

        arch = svc.create_reference_architecture(
            catalog_session.org_id,
            catalog_session.workspace_id,
            ReferenceArchitectureIn(
                name="Temp Arch",
                products=[ReferenceArchitectureProductItem(product_id=p1.id, role="Core")],
            ),
        )
        ok = svc.delete_reference_architecture(arch.id, catalog_session.workspace_id)
        assert ok is True
