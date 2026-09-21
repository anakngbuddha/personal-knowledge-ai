"""Minimal SAML assertion parser with HMAC integrity (no xmlsec dependency)."""

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
    raw = encoded_or_xml.strip()
    try:
        xml = base64.b64decode(raw, validate=True).decode("utf-8")
        if "<" not in xml:
            xml = encoded_or_xml
    except Exception:
        xml = encoded_or_xml

    if not allow_unsigned:
        verify_saml_signature(xml, secret, signature)

    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise InvalidTokenError("malformed SAML assertion") from exc

    issuer = ""
    name_id = ""
    audience: str | None = None
    not_on_or_after: datetime | None = None
    role = "viewer"
    org_id: str | None = None
    org_slug: str | None = None

    for node in root.iter():
        tag = _local(node.tag)
        text = (node.text or "").strip()
        if tag == "Issuer" and text:
            issuer = text
        elif tag == "NameID" and text:
            name_id = text
        elif tag == "Audience" and text:
            audience = text
        elif tag == "Conditions":
            not_on_or_after = _parse_time(node.attrib.get("NotOnOrAfter"))
        elif tag == "Attribute":
            name = (node.attrib.get("Name") or node.attrib.get("FriendlyName") or "").lower()
            values = [
                (child.text or "").strip()
                for child in list(node)
                if _local(child.tag) == "AttributeValue" and child.text
            ]
            value = values[0] if values else text
            if name in {"role", "http://schemas.microsoft.com/ws/2008/06/identity/claims/role"}:
                role = value
            elif name in {"org_id", "orgid"}:
                org_id = value
            elif name in {"org_slug", "organization"}:
                org_slug = value

    if issuer != expected_issuer:
        raise InvalidTokenError("saml issuer mismatch")
    if expected_audience and audience and audience != expected_audience:
        raise InvalidTokenError("saml audience mismatch")
    if not name_id:
        raise InvalidTokenError("saml NameID missing")
    if not_on_or_after is not None:
        now = datetime.now(timezone.utc)
        expiry = not_on_or_after if not_on_or_after.tzinfo else not_on_or_after.replace(tzinfo=timezone.utc)
        if now > expiry:
            raise InvalidTokenError("saml assertion expired")

    return SamlAssertion(
        issuer=issuer,
        name_id=name_id,
        audience=audience,
        not_on_or_after=not_on_or_after,
        role=role,
        org_id=org_id,
        org_slug=org_slug,
        raw_xml=xml,
    )
