"""Same-origin vendor crawl into the document pipeline.

robots.txt is a floor, not a terms-of-service grant. Registering a source does
not mean that vendor's terms allow bulk collection; that decision stays with
the operator who added the URL.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from datetime import timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, DuplicateDocument, SsrfBlocked
from app.core.logging import get_logger
from app.db.models import (
    Document,
    DocumentStatus,
    FreshnessAlert,
    FreshnessStatus,
    VendorSource,
    VendorSourcePage,
)
from app.documents.metadata import DocumentMetadataIn
from app.documents.service import create_document, enqueue_ingestion, find_previous_version
from app.documents.sniffing import sniff
from app.freshness.scraper import CheckResult, Fetcher, _now, content_digest, default_fetcher
from app.net.ssrf import fetch_robots, parse_robots, robots_url_for, validate_url
from app.security.labels import ApprovalState, Role, SourceType
from app.security.principal import Principal

logger = get_logger(__name__)


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []
        self.base_href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        found = {key.lower(): value for key, value in attrs if value}
        if tag.lower() == "base" and found.get("href"):
            self.base_href = found["href"]
        elif tag.lower() == "a" and found.get("href"):
            self.hrefs.append(found["href"].strip())


def extract_links(data: bytes, base_url: str) -> list[str]:
    """Collect absolute http(s) links. This does not extract page text."""
    parser = _AnchorParser()
    try:
        parser.feed(data.decode("utf-8", errors="replace"))
        parser.close()
    except Exception:  # noqa: BLE001 - a bad page should not abort the crawl
        logger.warning("could not read links from %s", base_url, exc_info=True)
        return []
    base = urljoin(base_url, parser.base_href) if parser.base_href else base_url
    links: list[str] = []
    for href in parser.hrefs:
        lowered = href.lower()
        if not href or lowered.startswith(("mailto:", "javascript:", "data:", "#")):
            continue
        absolute = urljoin(base, href)
        if urlparse(absolute).scheme.lower() not in {"http", "https"}:
            continue
        links.append(absolute)
    return links


def _origin(url: str) -> tuple[str, str, int | None]:
    parsed = urlparse(url)
    return (parsed.scheme.lower(), (parsed.hostname or "").lower().rstrip("."), parsed.port)


def _in_prefix(url: str, prefix: str | None) -> bool:
    if not prefix:
        return True
    normalized = prefix.strip()
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    path = urlparse(url).path or "/"
    if normalized == "/":
        return True
    trimmed = normalized.rstrip("/")
    return path == trimmed or path.startswith(trimmed + "/")


def _is_not_found(exc: SsrfBlocked) -> bool:
    return "HTTP 404" in (exc.message or "")


def _classify(raw: str, seed: str, prefix: str | None) -> tuple[str, str | None]:
    """Return (url, reason). reason is None when the URL may be fetched."""
    try:
        normalized, _ = validate_url(raw)
    except SsrfBlocked:
        return raw, "blocked"
    if _origin(normalized) != _origin(seed):
        return normalized, "off_origin"
    if not _in_prefix(normalized, prefix):
        return normalized, "prefix"
    return normalized, None


def _stable_filename(url: str, file_type: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    return f"vendor-{digest}.{file_type}"


def _system_principal(source: VendorSource) -> Principal:
    return Principal(
        org_id=source.org_id,
        user_id=None,
        role=Role.OWNER,
        account_refs=None,
        include_unapproved=True,
        label="freshness-crawl",
    )


def _load_robots(seed: str, fetch_fn: Fetcher):
    if fetch_fn is default_fetcher:
        return fetch_robots(seed)
    normalized, _ = validate_url(robots_url_for(seed))
    try:
        snapshot = fetch_fn(normalized)
    except SsrfBlocked as exc:
        if _is_not_found(exc):
            return parse_robots(b"")
        raise
    return parse_robots(snapshot.data)


def _pause(count: list[int]) -> None:
    delay = settings.freshness_request_delay_seconds
    if count[0] and delay > 0:
        time.sleep(delay)
    count[0] += 1


def _error(db: Session, source: VendorSource, message: str) -> CheckResult:
    source.status = FreshnessStatus.ERROR
    source.last_error = message[:2000]
    source.last_checked_at = _now()
    source.next_check_at = _now() + timedelta(seconds=source.check_interval_seconds)
    source.locked_by = None
    source.locked_at = None
    db.commit()
    return CheckResult(
        source_id=source.id,
        status=source.status,
        hash=source.last_hash,
        changed=False,
        alert_id=None,
        error=source.last_error,
    )


def _page_row(db: Session, source: VendorSource, url: str) -> VendorSourcePage:
    row = db.scalar(
        select(VendorSourcePage).where(
            VendorSourcePage.vendor_source_id == source.id,
            VendorSourcePage.url == url,
        )
    )
    if row is None:
        row = VendorSourcePage(org_id=source.org_id, vendor_source_id=source.id, url=url)
        db.add(row)
        db.flush()
    return row


def _reactivate(db: Session, document: Document) -> None:
    """Make a removed page visible to filename version matching again."""
    if document.is_current:
        return
    current = find_previous_version(db, document.workspace_id, document.original_filename)
    if current is None:
        document.is_current = True
        db.flush()


def _ingest(db: Session, source: VendorSource, url: str, data: bytes, file_type: str, *, user_initiated: bool) -> Document | None:
    approved = settings.freshness_auto_approve
    meta = DocumentMetadataIn(
        title=url[:512],
        vendor=(source.label or "")[:255] or None,
        source_type=str(SourceType.VENDOR_PAGE),
        source_url=url,
        approval_state=str(ApprovalState.APPROVED if approved else ApprovalState.DRAFT),
    )
    try:
        document = create_document(
            db,
            principal=_system_principal(source),
            original_filename=_stable_filename(url, file_type),
            data=data,
            mime_type="text/html" if file_type == "html" else None,
            metadata=meta,
            apply_auto_approve=False,
            allow_incomplete_approval=approved,
            workspace_id=source.workspace_id,
        )
    except DuplicateDocument as exc:
        document = db.get(Document, exc.existing_id) if exc.existing_id else None
        if document is None:
            logger.warning("crawl: duplicate of %s has no row", url)
            return None
    except AppError:
        logger.warning("crawl: ingest rejected %s", url, exc_info=True)
        return None
    except Exception:  # noqa: BLE001 - a bad page must not fail the hash check
        logger.exception("crawl: ingest failed %s", url)
        return None
    if document.status in {DocumentStatus.UPLOADED, DocumentStatus.FAILED}:
        try:
            enqueue_ingestion(db, document, user_initiated=user_initiated)
        except Exception:  # noqa: BLE001
            logger.exception("crawl: enqueue failed %s", url)
    return document


def _record_page(
    db: Session,
    source: VendorSource,
    url: str,
    data: bytes,
    *,
    previously_checked: bool,
    changes: list[dict],
    user_initiated: bool,
) -> None:
    kind = sniff(data).file_type
    digest = content_digest(data)
    page = _page_row(db, source, url)
    previous = page.last_hash
    if page.document_id and page.missing_at is not None:
        existing = db.get(Document, page.document_id)
        if existing is not None:
            _reactivate(db, existing)
    if previous == digest and page.document_id:
        page.last_seen_at = _now()
        page.missing_at = None
        return

    document: Document | None = None
    if kind:
        document = _ingest(db, source, url, data, kind, user_initiated=user_initiated)
        if document is None:
            if previously_checked and previous not in (None, digest):
                changes.append(
                    {
                        "url": url,
                        "change": "changed" if previous else "new",
                        "previous_hash": previous,
                        "new_hash": digest,
                    }
                )
            return

    page.last_hash = digest
    page.last_seen_at = _now()
    page.missing_at = None
    if document is not None:
        page.document_id = document.id
    if not previously_checked or previous == digest:
        return
    changes.append(
        {
            "url": url,
            "change": "new" if previous is None else "changed",
            "previous_hash": previous,
            "new_hash": digest,
        }
    )


def _retire_missing(
    db: Session,
    source: VendorSource,
    seen: set[str],
    robots_blocked: set[str],
    *,
    truncated: bool,
    previously_checked: bool,
    changes: list[dict],
) -> None:
    rows = list(
        db.scalars(select(VendorSourcePage).where(VendorSourcePage.vendor_source_id == source.id))
    )
    for page in rows:
        if page.url in seen or page.missing_at is not None:
            continue
        if truncated and page.url not in robots_blocked:
            continue
        page.missing_at = _now()
        if page.document_id:
            document = db.get(Document, page.document_id)
            if document is not None:
                document.is_current = False
        if previously_checked:
            changes.append(
                {
                    "url": page.url,
                    "change": "removed",
                    "previous_hash": page.last_hash,
                    "new_hash": None,
                }
            )


def crawl_source(
    db: Session,
    source: VendorSource,
    *,
    fetcher: Fetcher | None = None,
    user_initiated: bool = True,
) -> CheckResult:
    """Crawl the seed origin, ingest changed pages, and alert on what moved."""
    fetch_fn = fetcher or default_fetcher
    previously_checked = source.last_checked_at is not None or source.last_hash is not None
    previous_seed = source.last_hash
    prefix = (source.path_prefix or "").strip() or None
    requests = [0]

    try:
        seed, seed_reason = _classify(source.url, source.url, prefix)
    except SsrfBlocked as exc:
        return _error(db, source, str(exc.message or exc))
    if seed_reason == "blocked":
        return _error(db, source, "seed URL blocked by SSRF policy")
    if seed_reason:
        return _error(db, source, "seed URL is outside the crawl scope")

    try:
        _pause(requests)
        rules = _load_robots(seed, fetch_fn)
    except SsrfBlocked as exc:
        return _error(db, source, str(exc.message or exc))
    if not rules.allows(seed):
        return _error(db, source, "robots.txt disallows the seed URL")

    limit = max(1, settings.freshness_max_pages)
    max_depth = max(0, settings.freshness_max_depth)
    frontier: list[tuple[str, int]] = [(seed, 0)]
    queued = {seed}
    reached: dict[str, bytes] = {}
    robots_blocked: set[str] = set()
    seed_body: bytes | None = None
    seed_snapshot_etag: str | None = None
    seed_snapshot_modified: str | None = None

    while frontier and len(reached) < limit:
        requested, depth = frontier.pop(0)
        normalized, reason = _classify(requested, seed, prefix)
        if reason == "blocked":
            if requested == seed or normalized == seed:
                return _error(db, source, "seed URL blocked by SSRF policy")
            continue
        if reason:
            continue
        if not rules.allows(normalized):
            robots_blocked.add(normalized)
            if normalized == seed:
                return _error(db, source, "robots.txt disallows the seed URL")
            continue
        try:
            _pause(requests)
            checked, _ = validate_url(normalized)
            snapshot = fetch_fn(checked)
        except SsrfBlocked as exc:
            if normalized == seed:
                return _error(db, source, str(exc.message or exc))
            logger.info("crawl skipped %s: %s", normalized, exc.message)
            continue

        final = snapshot.final_url or checked
        final_url, final_reason = _classify(final, seed, prefix)
        if final_reason or not rules.allows(final_url):
            if normalized == seed:
                return _error(db, source, "seed redirected outside the crawl scope")
            if not final_reason and not rules.allows(final_url):
                robots_blocked.add(final_url)
            logger.info("crawl dropped %s after redirect to %s", normalized, final)
            continue

        reached[final_url] = snapshot.data
        if normalized == seed:
            seed_body = snapshot.data
            seed_snapshot_etag = snapshot.etag
            seed_snapshot_modified = snapshot.last_modified
        kind = sniff(snapshot.data).file_type
        if kind == "html" and depth < max_depth:
            for link in extract_links(snapshot.data, final_url):
                link_url, link_reason = _classify(link, seed, prefix)
                if link_reason:
                    continue
                if not rules.allows(link_url):
                    robots_blocked.add(link_url)
                    continue
                if link_url not in queued:
                    queued.add(link_url)
                    frontier.append((link_url, depth + 1))

    if seed_body is None:
        return _error(db, source, "seed URL was not fetched")

    changes: list[dict] = []
    for url, data in reached.items():
        _record_page(
            db,
            source,
            url,
            data,
            previously_checked=previously_checked,
            changes=changes,
            user_initiated=user_initiated,
        )
    _retire_missing(
        db,
        source,
        set(reached),
        robots_blocked,
        truncated=bool(frontier),
        previously_checked=previously_checked,
        changes=changes,
    )

    digest = content_digest(seed_body)
    alert_id: uuid.UUID | None = None
    source.last_hash = digest
    source.last_etag = seed_snapshot_etag
    source.last_modified_header = seed_snapshot_modified
    source.last_checked_at = _now()
    source.last_error = None
    source.next_check_at = _now() + timedelta(seconds=source.check_interval_seconds)
    source.locked_by = None
    source.locked_at = None
    if changes:
        source.status = FreshnessStatus.STALE
        alert = FreshnessAlert(
            org_id=source.org_id,
            vendor_source_id=source.id,
            kind="content_changed",
            previous_hash=previous_seed,
            new_hash=digest,
            details={"url": source.url, "bytes": len(seed_body), "pages": changes},
        )
        db.add(alert)
        db.flush()
        alert_id = alert.id
    else:
        source.status = FreshnessStatus.FRESH
    db.commit()
    return CheckResult(
        source_id=source.id,
        status=source.status,
        hash=digest,
        changed=alert_id is not None,
        alert_id=alert_id,
    )
