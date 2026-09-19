"""The SSRF fetcher's security boundary.

The classifier is tested against resolved addresses rather than hostnames, because
resolving is the step an attacker controls.
"""

import pytest

from app.core.errors import SsrfBlocked
from app.net.ssrf import classify_host, is_blocked_address, validate_url

BLOCKED_ADDRESSES = [
    ("127.0.0.1", "loopback"),
    ("127.1.2.3", "loopback"),
    ("::1", "loopback"),
    ("10.0.0.5", "private"),
    ("172.16.3.4", "private"),
    ("192.168.1.1", "private"),
    ("0.0.0.0", "private"),
    ("169.254.169.254", "metadata"),
    ("169.254.170.2", "metadata"),
    ("100.100.100.200", "metadata"),
    ("192.0.0.192", "metadata"),
    ("100.64.1.1", "carrier-grade NAT"),
    ("fd00::1", "private"),
    ("fe80::1", "link-local"),
    ("224.0.0.1", "multicast"),
    ("::ffff:127.0.0.1", "loopback"),
]

ALLOWED_ADDRESSES = ["93.184.216.34", "8.8.8.8", "2606:2800:220:1:248:1893:25c8:1946"]


@pytest.mark.parametrize(("address", "reason"), BLOCKED_ADDRESSES)
def test_blocked_addresses(address, reason):
    blocked, detail = is_blocked_address(address)
    assert blocked, address
    assert reason.split()[0].lower() in detail.lower()


@pytest.mark.parametrize("address", ALLOWED_ADDRESSES)
def test_public_addresses_are_allowed(address):
    blocked, _ = is_blocked_address(address)
    assert not blocked, address


def test_garbage_is_blocked_not_allowed():
    assert is_blocked_address("not-an-ip")[0] is True
    assert is_blocked_address("")[0] is True


def test_dns_rebinding_to_a_private_address_is_blocked():
    """A public hostname is worthless as a signal; the resolved address decides."""
    assert classify_host("totally-legit.example.com", ["10.0.0.1"])
    assert classify_host("ok.example.com", ["1.2.3.4"]) == []


def test_split_horizon_is_blocked_if_any_address_is_internal():
    reasons = classify_host("mixed.example.com", ["1.2.3.4", "127.0.0.1"])
    assert reasons and "loopback" in reasons[0]


def test_internal_names_are_blocked_without_resolving():
    for host in ("localhost", "service.internal", "printer.local", "app.localhost"):
        assert classify_host(host), host


def test_non_http_schemes_are_blocked():
    for url in ("file:///etc/passwd", "gopher://x/", "ftp://host/f", "data:text/plain,hi"):
        with pytest.raises(SsrfBlocked, match="scheme"):
            validate_url(url, allow_private=True)


def test_embedded_credentials_are_blocked():
    with pytest.raises(SsrfBlocked, match="credentials"):
        validate_url("http://user:secret@example.com/", allow_private=True)


def test_unexpected_ports_are_blocked():
    with pytest.raises(SsrfBlocked, match="port"):
        validate_url("http://example.com:22/", allow_private=True)
    validate_url("https://example.com:8443/x", allow_private=True)


def test_url_is_normalised_and_fragment_dropped():
    normalized, host = validate_url("HTTPS://Example.com/a?b=1#frag", allow_private=True)
    assert normalized == "https://Example.com/a?b=1"
    assert host == "example.com"
