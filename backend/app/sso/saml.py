"""Disabled legacy SAML interface; strict XML Signature processing is in standards.py."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

from app.security.jwt import InvalidTokenError

_TAG = re.compile(r"\{[^}]+\}")


@dataclass(frozen=True)
class SamlAssertion:
    issuer: str
    name_id: str
    audience: str | None
    not_on_or_after: datetime | None
    role: str
    org_id: str | None
    org_slug: str | None
    raw_xml: str


def _local(tag: str) -> str:
    return _TAG.sub("", tag)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def sign_saml_assertion(xml: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), xml.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_saml_signature(xml: str, secret: str, signature: str | None) -> None:
    if not signature:
        raise InvalidTokenError("saml signature missing")
    expected = sign_saml_assertion(xml, secret)
    if not hmac.compare_digest(expected, signature.strip().lower()):
        raise InvalidTokenError("saml signature mismatch")


def parse_saml_assertion(
    encoded_or_xml: str,
    *,
    expected_issuer: str,
    expected_audience: str | None,
    secret: str,
    signature: str | None,
    allow_unsigned: bool = False,
) -> SamlAssertion:
    raise InvalidTokenError("legacy HMAC SAML is disabled; use the strict XML Signature ACS")
