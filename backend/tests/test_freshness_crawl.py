"""Vendor-site crawl: scope, robots, SSRF, and document versioning."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.errors import SsrfBlocked
from app.db.models import (
    AccessGrant,
    AuditLog,
    Document,
    FreshnessAlert,
    IngestionJob,
    Organization,
    VendorSource,
    VendorSourcePage,
    Workspace,
)
from app.db.session import get_db
from app.freshness.crawl import crawl_source
from app.freshness.scraper import FetchSnapshot, create_source
from app.jobs.worker import execute_claimed
from app.main import app
from app.net.ssrf import validate_url
from app.security.jwt import mint_token
from app.security.labels import Role

client = TestClient(app)

SEED = "https://vendor.example/docs/"
PAGE_A = "https://vendor.example/docs/a"
PAGE_B = "https://vendor.example/docs/b"
PRIVATE = "https://vendor.example/docs/private"
BLOG = "https://vendor.example/blog/out"
OFF = "https://off.example/secret"
SSRF = "http://127.0.0.1/latest"
ROBOTS = "https://vendor.example/robots.txt"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):  # noqa: ARG001
    return "JSON"


def _html(*hrefs: str, body: str = "page") -> bytes:
    links = "".join(f'<a href="{href}">{href}</a>' for href in hrefs)
    return f"<html><body><h1>{body}</h1>{links}</body></html>".encode()


def _site() -> dict[str, bytes]:
    return {
        ROBOTS: b"User-agent: *\nDisallow: /docs/private\n",
        SEED: _html(PAGE_A, PAGE_B, PRIVATE, BLOG, OFF, SSRF, body="home"),
        PAGE_A: _html(PAGE_B, body="alpha"),
        PAGE_B: _html(body="beta"),
        PRIVATE: _html(body="secret"),
        BLOG: _html(body="blog"),
    }


def _engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


@pytest.fixture
def crawl_db(monkeypatch):
    monkeypatch.setattr(settings, "freshness_request_delay_seconds", 0)
    monkeypatch.setattr(settings, "freshness_max_pages", 50)
    monkeypatch.setattr(settings, "freshness_max_depth", 2)
    monkeypatch.setattr(settings, "freshness_auto_approve", True)
    monkeypatch.setattr(settings, "auto_approve_uploads", False)
    monkeypatch.setattr(settings, "freshness_worker_enabled", False)

    def resolve(host: str) -> list[str]:
        if host in {"127.0.0.1", "169.254.169.254"}:
            return [host]
        if host in {"vendor.example", "off.example"}:
            return ["93.184.216.34"]
        raise SsrfBlocked(f"could not resolve host {host!r}")

    monkeypatch.setattr("app.net.ssrf.resolve_host", resolve)

    engine = _engine()
    from app.db.models import Base

    Base.metadata.create_all(
        engine,
        tables=[
            Organization.__table__,
            AccessGrant.__table__,
            Workspace.__table__,
            Document.__table__,
            VendorSource.__table__,
            VendorSourcePage.__table__,
            FreshnessAlert.__table__,
            IngestionJob.__table__,
            AuditLog.__table__,
        ],
    )
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = Session()
    org = Organization(id=uuid.uuid4(), slug="crawl-org", name="Crawl")
    db.add(org)
    db.flush()
    workspace = Workspace(id=uuid.uuid4(), org_id=org.id, name="Desk")
    db.add(workspace)
    db.commit()
    db.org_id = org.id
    db.workspace_id = workspace.id
    db.Session = Session
    yield db
    db.close()


def _source(db, **kwargs):
    return create_source(
        db,
        org_id=db.org_id,
        workspace_id=db.workspace_id,
        label="Vendor docs",
        url=SEED,
        path_prefix="/docs",
        **kwargs,
    )


def _fetcher(pages: dict[str, bytes], fetched: list[str]):
    def fetch(url: str) -> FetchSnapshot:
        fetched.append(url)
        if url not in pages:
            raise SsrfBlocked(f"{url} returned HTTP 404")
        return FetchSnapshot(data=pages[url], final_url=url)

    return fetch


def _current_docs(db) -> list[Document]:
    return list(db.scalars(select(Document).where(Document.is_current.is_(True))))


def test_crawl_stays_in_scope_and_ingests_pages(crawl_db, monkeypatch):
    db = crawl_db
    pages = _site()
    fetched: list[str] = []
    blocked: list[str] = []
    real_validate = validate_url

    def spy(url: str, **kwargs):
        try:
            return real_validate(url, **kwargs)
        except SsrfBlocked:
            blocked.append(url)
            raise

    monkeypatch.setattr("app.freshness.crawl.validate_url", spy)
    source = _source(db)
    result = crawl_source(db, source, fetcher=_fetcher(pages, fetched))

    assert result.changed is False
    assert result.status == "fresh"
    assert SSRF not in fetched
    assert OFF not in fetched
    assert PRIVATE not in fetched
    assert BLOG not in fetched
    assert any("127.0.0.1" in url for url in blocked)
    assert set(fetched) == {ROBOTS, SEED, PAGE_A, PAGE_B}

    docs = _current_docs(db)
    assert len(docs) == 3
    assert {doc.approval_state for doc in docs} == {"approved"}
    assert {doc.source_type for doc in docs} == {"vendor_page"}
    assert {doc.workspace_id for doc in docs} == {db.workspace_id}
    assert db.scalar(select(FreshnessAlert)) is None

    again = crawl_source(db, source, fetcher=_fetcher(pages, fetched))
    assert again.changed is False
    assert len(_current_docs(db)) == 3
    assert len(list(db.scalars(select(Document)))) == 3


def test_changed_page_supersedes_and_removed_page_leaves_the_corpus(crawl_db):
    db = crawl_db
    pages = _site()
    fetched: list[str] = []
    source = _source(db)
    crawl_source(db, source, fetcher=_fetcher(pages, fetched))

    page_b = db.scalar(select(VendorSourcePage).where(VendorSourcePage.url == PAGE_B))
    assert page_b is not None and page_b.document_id is not None
    original = db.get(Document, page_b.document_id)
    assert original is not None

    pages[PAGE_B] = _html(body="beta-v2")
    changed = crawl_source(db, source, fetcher=_fetcher(pages, fetched))
    assert changed.changed is True
    db.refresh(original)
    db.refresh(page_b)
    successor = db.get(Document, page_b.document_id)
    assert successor is not None
    assert successor.id != original.id
    assert successor.supersedes_id == original.id
    assert successor.is_current is True
    assert original.is_current is False
    assert successor.original_filename == original.original_filename

    alert = db.scalar(select(FreshnessAlert))
    assert alert is not None
    assert any(item["url"] == PAGE_B and item["change"] == "changed" for item in alert.details["pages"])

    pages[SEED] = _html(PAGE_A, PRIVATE, BLOG, OFF, SSRF, body="home")
    pages[PAGE_A] = _html(body="alpha")
    removed = crawl_source(db, source, fetcher=_fetcher(pages, fetched))
    assert removed.changed is True
    db.refresh(successor)
    assert successor.is_current is False
    removal = db.scalars(select(FreshnessAlert).order_by(FreshnessAlert.created_at)).all()[-1]
    assert any(item["url"] == PAGE_B and item["change"] == "removed" for item in removal.details["pages"])

    crawl_source(db, source, fetcher=_fetcher(pages, fetched))
    alerts = list(db.scalars(select(FreshnessAlert)))
    assert len(alerts) == 2


def test_robots_disallow_of_the_seed_skips_the_crawl(crawl_db):
    db = crawl_db
    pages = _site()
    pages[ROBOTS] = b"User-agent: *\nDisallow: /\n"
    fetched: list[str] = []
    source = _source(db)
    result = crawl_source(db, source, fetcher=_fetcher(pages, fetched))
    assert result.status == "error"
    assert "robots.txt" in (result.error or "")
    assert fetched == [ROBOTS]
    assert list(db.scalars(select(Document))) == []


def test_missing_robots_still_crawls(crawl_db):
    db = crawl_db
    pages = _site()
    del pages[ROBOTS]
    fetched: list[str] = []
    source = _source(db)
    result = crawl_source(db, source, fetcher=_fetcher(pages, fetched))
    assert result.status == "fresh"
    assert ROBOTS in fetched
    assert PAGE_A in fetched


def test_page_cap_does_not_fetch_the_rest_of_the_site(crawl_db, monkeypatch):
    db = crawl_db
    monkeypatch.setattr(settings, "freshness_max_pages", 1)
    pages = _site()
    fetched: list[str] = []
    source = _source(db)
    crawl_source(db, source, fetcher=_fetcher(pages, fetched))
    assert SEED in fetched
    assert PAGE_A not in fetched
    assert PAGE_B not in fetched
    assert len(_current_docs(db)) == 1


def test_draft_setting_leaves_pages_unapproved(crawl_db, monkeypatch):
    db = crawl_db
    monkeypatch.setattr(settings, "freshness_auto_approve", False)
    pages = {ROBOTS: b"User-agent: *\nAllow: /\n", SEED: _html(body="only")}
    source = _source(db)
    crawl_source(db, source, fetcher=_fetcher(pages, []))
    docs = _current_docs(db)
    assert len(docs) == 1
    assert docs[0].approval_state == "draft"


def test_check_route_enqueues_and_does_not_fetch(crawl_db, monkeypatch):
    db = crawl_db

    def boom(url, **kwargs):  # noqa: ARG001
        raise AssertionError(f"fetched {url}")

    monkeypatch.setattr("app.net.ssrf.fetch", boom)

    def _get_db():
        inner = db.Session()
        try:
            yield inner
        finally:
            inner.close()

    app.dependency_overrides[get_db] = _get_db
    try:
        token = mint_token(org_id=db.org_id, user_id=uuid.uuid4(), role=Role.SOLUTIONS_ENGINEER)
        created = client.post(
            "/freshness/sources",
            headers={"Authorization": f"Bearer {token}"},
            json={"label": "Docs", "url": SEED, "path_prefix": "/docs"},
        )
        assert created.status_code == 201, created.text
        source_id = created.json()["id"]
        checked = client.post(
            f"/freshness/sources/{source_id}/check",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert checked.status_code == 200, checked.text
        body = checked.json()
        assert body["status"] == "queued"
        assert body["changed"] is False
        assert body["job_id"]
        job = db.get(IngestionJob, uuid.UUID(body["job_id"]))
        assert job is not None
        assert job.kind == "freshness_crawl"
        assert job.document_id is None
        assert job.payload["vendor_source_id"] == source_id
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_worker_dispatches_crawl_jobs(crawl_db, monkeypatch):
    db = crawl_db
    source = _source(db)
    seen: list[uuid.UUID] = []

    def fake_crawl(session, row, fetcher=None):  # noqa: ARG001
        seen.append(row.id)
        from app.freshness.scraper import CheckResult

        return CheckResult(source_id=row.id, status="fresh", hash=None, changed=False, alert_id=None)

    monkeypatch.setattr("app.freshness.crawl.crawl_source", fake_crawl)
    job = IngestionJob(
        org_id=db.org_id,
        document_id=None,
        kind="freshness_crawl",
        payload={"vendor_source_id": str(source.id)},
    )
    db.add(job)
    db.commit()
    execute_claimed(db, job)
    assert seen == [source.id]
