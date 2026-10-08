"""Pure-ASGI middleware: request IDs, access log, security headers, last-resort 500 handler."""

import json
import re
import time
import uuid

from starlette.datastructures import MutableHeaders

from app.core.errors import error_body
from app.core.logging import get_logger, request_id_ctx

log = get_logger("app.http")
_RID_RE = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


class RequestContextMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope.get("headers") or []).get(b"x-request-id", b"").decode("latin-1")
        rid = incoming if _RID_RE.match(incoming) else uuid.uuid4().hex
        token = request_id_ctx.set(rid)
        started = time.perf_counter()
        state = {"status": 500, "started": False}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                state["status"] = message["status"]
                state["started"] = True
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = rid
                for key, value in SECURITY_HEADERS.items():
                    if key not in headers:
                        headers[key] = value
                if "cache-control" not in headers:
                    headers["Cache-Control"] = "no-store"
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            log.exception("unhandled_error")
            if state["started"]:
                raise
            body = json.dumps(error_body("INTERNAL_ERROR", "Unexpected server error")).encode()
            await send_wrapper(
                {"type": "http.response.start", "status": 500, "headers": [(b"content-type", b"application/json")]}
            )
            await send_wrapper({"type": "http.response.body", "body": body})
        finally:
            path = scope.get("path", "")
            if not path.startswith("/api/v1/health"):
                log.info(
                    "request",
                    extra={
                        "fields": {
                            "method": scope.get("method"),
                            "path": path,
                            "status": state["status"],
                            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                        }
                    },
                )
            request_id_ctx.reset(token)
