"""SSRF-safe URL fetching.

Project_Plan.md Phase 1: "URL ingestion through an SSRF-safe fetcher: private IP
ranges, cloud metadata endpoints, and redirects to internal hosts all denied."

Design notes worth knowing before changing anything here:

* The address check runs on the **resolved** IPs, not on the hostname. Blocking
  "localhost" by name is trivially bypassed by any DNS record pointing at 127.0.0.1.
* Every redirect hop is re-resolved and re-validated. A public host redirecting to
  169.254.169.254 is the classic bypass, and it is why redirects are followed
  manually instead of handing the whole chain to httpx.
* The classifier (`classify_host`) is pure and unit-tested on its own. The fetcher
  is the thin, network-touching part.
* Denied by default. `URL_FETCH_ALLOW_PRIVATE_IPS` exists for tests and says so.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

from app.core.config import settings
from app.core.errors import SsrfBlocked
from app.core.logging import get_logger

logger = get_logger(__name__)

ALLOWED_SCHEMES = frozenset({"http", "https"})
ALLOWED_PORTS = frozenset({80, 443, 8080, 8443})

# Cloud instance-metadata services. Link-local already covers 169.254.169.254, but
# these are listed explicitly so the denial reason is unambiguous in a log.
METADATA_ADDRESSES = frozenset(
    {
        "169.254.169.254",  # AWS / Azure / GCP / DigitalOcean
        "169.254.170.2",  # AWS ECS task metadata
        "100.100.100.200",  # Alibaba Cloud
        "192.0.0.192",  # Oracle Cloud
        "fd00:ec2::254",  # AWS IMDSv2 over IPv6
    }
)

MAX_FETCH_BYTES = 25 * 1024 * 1024
ALLOWED_CONTENT_TYPES = (
    "text/html",
    "text/plain",
    "text/markdown",
    "application/pdf",
    "application/xhtml+xml",
    "application/vnd.openxmlformats-officedocument",
    "application/vnd.ms-excel",
    "application/octet-stream",
)


@dataclass(frozen=True)
class FetchedResource:
    url: str
    final_url: str
    data: bytes
    content_type: str | None
    redirects: tuple[str, ...] = ()


def is_blocked_address(address: str) -> tuple[bool, str]:
    """Pure predicate over a single IP literal. This is the actual security boundary."""
    if address in METADATA_ADDRESSES:
        return True, "cloud instance metadata endpoint"
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return True, f"not an IP address: {address!r}"

    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return is_blocked_address(str(ip.ipv4_mapped))

    for condition, reason in (
        (ip.is_loopback, "loopback address"),
        (ip.is_link_local, "link-local address"),
        (ip.is_multicast, "multicast address"),
        (ip.is_private, "private address range"),
        (ip.is_reserved, "reserved address"),
        (ip.is_unspecified, "unspecified address"),
    ):
        if condition:
            return True, reason
    # Carrier-grade NAT: not "private" by ipaddress, still not the public internet.
    if ip.version == 4 and ip in ipaddress.ip_network("100.64.0.0/10"):
        return True, "carrier-grade NAT range"
    if ip.version == 6 and ip in ipaddress.ip_network("fc00::/7"):
        return True, "IPv6 unique local address"
    return False, ""


def resolve_host(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise SsrfBlocked(f"could not resolve host {host!r}: {exc}") from exc
    return sorted({info[4][0] for info in infos})


def classify_host(host: str, addresses: list[str] | None = None) -> list[str]:
    """Return the denial reasons for a host. Empty list means allowed.

    Addresses may be injected so the classifier is testable without DNS.
    """
    if not host:
        return ["missing host"]
    if host.lower() in {"localhost", "localhost.localdomain"} or host.lower().endswith(
        (".localhost", ".internal", ".local")
    ):
        return [f"host {host!r} is an internal name"]

    resolved = addresses if addresses is not None else resolve_host(host)
    if not resolved:
        return [f"host {host!r} resolved to no addresses"]

    reasons: list[str] = []
    for address in resolved:
        blocked, reason = is_blocked_address(address)
        if blocked:
            reasons.append(f"{address} is a {reason}")
    return reasons


def validate_url(url: str, *, allow_private: bool | None = None) -> tuple[str, str]:
    """Validate a single URL. Returns (normalized_url, host)."""
    allow_private = (
        settings.url_fetch_allow_private_ips if allow_private is None else allow_private
    )
    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise SsrfBlocked(
            f"scheme {parsed.scheme or '(none)'!r} is not allowed "
            f"(allowed: {', '.join(sorted(ALLOWED_SCHEMES))})"
        )
    host = parsed.hostname or ""
    port = parsed.port
    if port is not None and port not in ALLOWED_PORTS:
        raise SsrfBlocked(f"port {port} is not allowed")
    if parsed.username or parsed.password:
        raise SsrfBlocked("credentials embedded in a URL are not allowed")

    if not allow_private:
        reasons = classify_host(host)
        if reasons:
            raise SsrfBlocked(f"refusing to fetch {host!r}: {'; '.join(reasons)}")

    normalized = urlunparse(
        (parsed.scheme.lower(), parsed.netloc, parsed.path or "/", "", parsed.query, "")
    )
    return normalized, host


def fetch(url: str, *, max_bytes: int = MAX_FETCH_BYTES) -> FetchedResource:
    """Fetch a URL, validating every redirect hop."""
    import httpx

    if not settings.url_fetch_enabled:
        raise SsrfBlocked("URL ingestion is disabled (URL_FETCH_ENABLED=false)")

    current, _ = validate_url(url)
    original = current
    redirects: list[str] = []

    with httpx.Client(
        follow_redirects=False,
        timeout=settings.url_fetch_timeout_seconds,
        headers={"User-Agent": "PersonalKnowledgeAI/1.0 (+collateral ingestion)"},
    ) as client:
        for _ in range(settings.url_fetch_max_redirects + 1):
            try:
                response = client.get(current)
            except httpx.HTTPError as exc:
                raise SsrfBlocked(f"fetch failed for {current}: {exc}") from exc

            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise SsrfBlocked(f"{current} returned a redirect with no Location header")
                # Re-validate the destination. This is the hop that bypasses a
                # hostname-only allowlist, so it gets the full check again.
                current, _ = validate_url(str(response.next_request.url))
                redirects.append(current)
                continue

            if response.status_code >= 400:
                raise SsrfBlocked(f"{current} returned HTTP {response.status_code}")

            content_type = (response.headers.get("content-type") or "").split(";")[0].strip()
            if content_type and not content_type.startswith(ALLOWED_CONTENT_TYPES):
                raise SsrfBlocked(f"content type {content_type!r} is not accepted")

            data = response.content
            if len(data) > max_bytes:
                raise SsrfBlocked(f"response exceeds {max_bytes} bytes")
            return FetchedResource(
                url=original,
                final_url=current,
                data=data,
                content_type=content_type or None,
                redirects=tuple(redirects),
            )

    raise SsrfBlocked(f"too many redirects (limit {settings.url_fetch_max_redirects})")
