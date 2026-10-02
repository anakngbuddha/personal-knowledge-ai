"""Security event log for authentication, with simple alert thresholds.

Authenticated actions already write audit rows. Logins, signups and failures happen
before there is a tenant, so they go to the `app.security.events` logger as
structured key=value lines. Emails are logged as a truncated SHA-256, never in clear.
When failures cross a threshold, a `security_alert` WARNING is emitted once per
threshold crossing; route that logger to your alerting (Render log streams, Datadog,
etc.).
"""

from __future__ import annotations

import hashlib

from app.core.config import settings
from app.core.logging import get_logger
from app.security import auth_throttle

logger = get_logger("app.security.events")


def email_ref(email: str | None) -> str:
    if not email:
        return "-"
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:16]


def _emit(level: str, event: str, **fields: object) -> None:
    parts = " ".join(f"{k}={str(v).replace(' ', '_')[:128]}" for k, v in fields.items())
    getattr(logger, level)("security_event event=%s %s", event, parts)


def _alert_on_threshold(kind: str, key: str, count: int, threshold: int, **fields: object) -> None:
    if threshold > 0 and count >= threshold and count % threshold == 0:
        _emit("warning", "security_alert", kind=kind, key=key, count=count, **fields)


def login_failed(ip: str, email: str, reason: str) -> None:
    window = float(settings.auth_login_failure_window_seconds)
    per_ip = auth_throttle.record("events:login_fail:ip", ip, window)
    total = auth_throttle.record("events:login_fail:all", "all", window)
    _emit("info", "login_failed", ip=ip, account=email_ref(email), reason=reason)
    _alert_on_threshold("failed_logins_from_ip", ip, per_ip, settings.auth_alert_failed_logins_per_ip, window_s=int(window))
    _alert_on_threshold("failed_logins_global", "all", total, settings.auth_alert_failed_logins_global, window_s=int(window))


def login_throttled(ip: str, email: str | None, scope: str) -> None:
    _emit("warning", "login_throttled", ip=ip, account=email_ref(email), scope=scope)


def login_succeeded(ip: str, email: str, org_id: object, user_id: object) -> None:
    _emit("info", "login_succeeded", ip=ip, account=email_ref(email), org=org_id, user=user_id)


def signup_attempt(ip: str, email: str, outcome: str) -> None:
    window = 3600.0
    level = "info" if outcome == "created" else "warning" if outcome in ("disabled", "throttled") else "info"
    _emit(level, "signup", ip=ip, account=email_ref(email), outcome=outcome)
    if outcome == "created":
        count = auth_throttle.record("events:signup:all", "all", window)
        _alert_on_threshold("signups_global", "all", count, settings.auth_alert_signups_per_hour, window_s=int(window))


def sso_failed(ip: str, protocol: str) -> None:
    window = float(settings.auth_login_failure_window_seconds)
    per_ip = auth_throttle.record("events:sso_fail:ip", ip, window)
    _emit("info", "sso_failed", ip=ip, protocol=protocol)
    _alert_on_threshold("failed_sso_from_ip", ip, per_ip, settings.auth_alert_failed_logins_per_ip, window_s=int(window))


def member_added(actor: object, org_id: object, account: str, outcome: str) -> None:
    _emit("info", "member_add", actor=actor, org=org_id, account=email_ref(account), outcome=outcome)
