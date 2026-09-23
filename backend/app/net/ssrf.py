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

USER_AGENT = "PersonalKnowledgeAI/1.0 (+collateral ingestion)"
ROBOTS_PRODUCT_TOKEN = "PersonalKnowledgeAI"

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


@dataclass(frozen=True)
class RobotsGroup:
    agents: tuple[str, ...]
    rules: tuple[tuple[bool, str], ...]


@dataclass(frozen=True)
class RobotsRules:
    """Parsed robots.txt. An empty rule set allows every path."""

    groups: tuple[RobotsGroup, ...] = ()

    def allows(self, url: str, product_token: str = ROBOTS_PRODUCT_TOKEN) -> bool:
        rules = _rules_for_token(self.groups, product_token)
        if not rules:
            return True
        parsed = urlparse(url)
        path = parsed.path or "/"
        query = parsed.query
        best_len = -1
        best_allow = True
        for allowed, pattern in rules:
            if not pattern:
                continue
            target = f"{path}?{query}" if "?" in pattern else path
            if not _robots_pattern_matches(target, pattern):
                continue
            if len(pattern) > best_len or (len(pattern) == best_len and allowed):
                best_len = len(pattern)
                best_allow = allowed
        return True if best_len < 0 else best_allow


def robots_url_for(url: str) -> str:
    parsed = urlparse(url.strip())
    return urlunparse((parsed.scheme.lower(), parsed.netloc, "/robots.txt", "", "", ""))


def parse_robots(data: bytes | str) -> RobotsRules:
    """Parse the subset of robots.txt we honor: grouped Allow and Disallow."""
    text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data
    groups: list[RobotsGroup] = []
    agents: list[str] = []
    rules: list[tuple[bool, str]] = []

    def flush() -> None:
        nonlocal agents, rules
        if agents:
            groups.append(RobotsGroup(agents=tuple(agents), rules=tuple(rules)))
        agents = []
        rules = []

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            flush()
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            if rules:
                flush()
            if value:
                agents.append(value)
        elif key in {"allow", "disallow"} and agents:
            rules.append((key == "allow", value))
    flush()
    return RobotsRules(groups=tuple(groups))


def fetch_robots(url: str) -> RobotsRules:
    """Fetch `{origin}/robots.txt`. HTTP 404 means the origin has no rules.

    Any other failure is raised. A missing or blocked robots file is not
    treated as permission to crawl.
    """
    target = robots_url_for(url)
    try:
        resource = fetch(target, max_bytes=settings.freshness_max_bytes)
    except SsrfBlocked as exc:
        if "HTTP 404" in (exc.message or ""):
            return RobotsRules()
        raise
    return parse_robots(resource.data)


def _rules_for_token(groups: tuple[RobotsGroup, ...], product_token: str) -> tuple[tuple[bool, str], ...]:
    token = product_token.strip().lower()
    specific: list[RobotsGroup] = []
    wildcard: list[RobotsGroup] = []
    for group in groups:
        named = [agent for agent in group.agents if agent != "*"]
        if any(token.startswith(agent.lower()) for agent in named if agent):
            specific.append(group)
        elif any(agent == "*" for agent in group.agents):
            wildcard.append(group)
    chosen = specific or wildcard
    rules: list[tuple[bool, str]] = []
    for group in chosen:
        rules.extend(group.rules)
    return tuple(rules)


def _robots_pattern_matches(path: str, pattern: str) -> bool:
    import re

    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    if body == "":
        return False
    regex = "".join(".*" if char == "*" else re.escape(char) for char in body)
    if anchored:
        regex += "$"
    return re.match(regex, path) is not None


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
        headers={"User-Agent": USER_AGENT},
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
