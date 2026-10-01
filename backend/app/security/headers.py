"""Security headers and a bounded request body before multipart parsing."""
import uuid
from starlette.responses import JSONResponse
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class SecurityMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = uuid.uuid4().hex
        budget = settings.max_upload_bytes * 4 + 1024 * 1024
        total = 0
        started = False
        async def limited_receive():
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > budget:
                raise BodyTooLarge()
            return message
        async def secure_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = list(message.get("headers", []))
                headers += [(b"x-content-type-options", b"nosniff"), (b"x-frame-options", b"DENY"),
                            (b"referrer-policy", b"no-referrer"), (b"x-request-id", request_id.encode()),
                            (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'; base-uri 'none'"),
                            (b"cache-control", b"no-store")]
                if settings.environment.lower() == "production":
                    headers.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                message["headers"] = headers
            await send(message)
        headers = dict(scope.get("headers", []))
        try:
            declared_size = int(headers.get(b"content-length", b"0"))
        except ValueError:
            declared_size = budget + 1
        if declared_size < 0 or declared_size > budget:
            return await JSONResponse({"detail": "request size limit exceeded"}, status_code=413)(scope, receive, secure_send)
        try:
            await self.app(scope, limited_receive, secure_send)
        except BodyTooLarge:
            if started:
                raise
            await JSONResponse({"detail": "request size limit exceeded"}, status_code=413)(scope, receive, secure_send)
        except Exception:
            logger.exception("request failed request_id=%s", request_id)
            if started:
                raise
            await JSONResponse({"detail": "request failed"}, status_code=500)(scope, receive, secure_send)


class BodyTooLarge(Exception):
    pass
