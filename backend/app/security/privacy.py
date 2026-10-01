"""Bounded, secret-aware durable audit payloads and log messages."""
import json
import math
import re

_SENSITIVE = re.compile(r"password|secret|token|authorization|cookie|credential|api.?key|body|content|email|filename|url|account_ref|error", re.I)
_BEARER = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_KEY_VALUE = re.compile(r"(?i)(password|secret|token|api[_-]?key|authorization|cookie)([\"']?\s*[:=]\s*[\"']?)[^\s,;&\"']+")


def redact_text(value: str) -> str:
    value = _BEARER.sub("Bearer [REDACTED]", value)
    value = _JWT.sub("[REDACTED]", value)
    value = _KEY_VALUE.sub(r"\1\2[REDACTED]", value)
    value = re.sub(r"https?://[^\s\"'<>]+", "[REDACTED_URL]", value)
    value = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[REDACTED]", value)
    value = re.sub(r"-----BEGIN (?:RSA )?PRIVATE KEY-----.*?-----END (?:RSA )?PRIVATE KEY-----", "[REDACTED]", value, flags=re.S)
    # Connection strings can contain credentials even without a named password.
    return re.sub(r"(\w+://)[^\s/@]+:[^\s/@]+@", r"\1[REDACTED]@", value)


def audit_details(value, depth=0):
    if depth > 4:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        result = {str(k)[:80]: "[REDACTED]" if _SENSITIVE.search(str(k)) else audit_details(v, depth+1) for k, v in list(value.items())[:50]}
    elif isinstance(value, (list, tuple)):
        result = [audit_details(v, depth+1) for v in value[:50]]
    elif isinstance(value, str):
        result = redact_text(value)[:500]
    elif isinstance(value, float) and not math.isfinite(value):
        result = "[UNSUPPORTED]"
    elif value is None or isinstance(value, (bool, int, float)):
        result = value
    else:
        result = "[UNSUPPORTED]"
    if len(json.dumps(result, default=str, allow_nan=False).encode()) > 8192:
        return {"truncated": True}
    return result
