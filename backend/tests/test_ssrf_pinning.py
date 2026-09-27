"""DNS-rebinding and body-size protections in the SSRF fetcher (audit finding 11)."""

from __future__ import annotations

import httpx
import pytest

from app.core.errors import SsrfBlocked
from app.net import ssrf


@pytest.fixture
def flipping_dns(monkeypatch):
    calls: list[str] = []

    def resolve(host: str) -> list[str]:
        calls.append(host)
        if host == "internal.example":
            return ["10.0.0.5"]
        # First answer is public, any later answer rebinds to loopback.
        return ["93.184.216.34"] if calls.count(host) == 1 else ["127.0.0.1"]

    monkeypatch.setattr("app.net.ssrf.resolve_host", resolve)
    return calls


def test_connection_goes_to_the_validated_address(flipping_dns):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, headers={"content-type": "text/plain"}, content=b"ok")

    result = ssrf.fetch("https://vendor.example/docs", transport=httpx.MockTransport(handler))
    assert result.data == b"ok"
    assert flipping_dns.count("vendor.example") == 1  # resolved once, never re-resolved
    assert seen[0].url.host == "93.184.216.34"
    assert seen[0].headers["host"] == "vendor.example"
    assert seen[0].extensions.get("sni_hostname") == "vendor.example"


def test_redirect_to_an_internal_host_is_blocked(flipping_dns):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://internal.example/admin"})

    with pytest.raises(SsrfBlocked, match="10.0.0.5"):
        ssrf.fetch("https://vendor.example/", transport=httpx.MockTransport(handler))


def test_declared_oversized_body_is_refused(flipping_dns):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/plain"}, content=b"x" * 2048)

    with pytest.raises(SsrfBlocked, match="exceeds"):
        ssrf.fetch("https://vendor.example/", max_bytes=1000, transport=httpx.MockTransport(handler))


def test_streamed_oversized_body_is_aborted(flipping_dns):
    sent: list[int] = []

    def body():
        for _ in range(10):
            sent.append(1)
            yield b"x" * 600

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/plain"}, content=body())

    with pytest.raises(SsrfBlocked, match="exceeds"):
        ssrf.fetch("https://vendor.example/", max_bytes=1000, transport=httpx.MockTransport(handler))
    assert len(sent) < 10
