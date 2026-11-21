"""Shared bearer authorization for the local assistant API."""

from __future__ import annotations

import hmac
import json
import time

from starlette.types import ASGIApp, Receive, Scope, Send


class APIAuthorizationMiddleware:
    """Require the process-scoped token for every non-public API operation."""

    def __init__(self, app: ASGIApp, api_prefix: str) -> None:
        self.app = app
        self.api_prefix = api_prefix.rstrip("/")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET").upper()
        if not path.startswith(f"{self.api_prefix}/") or self._is_public(path, method):
            await self.app(scope, receive, send)
            return

        application = scope.get("app")
        try:
            settings = application.state.settings
        except (AttributeError, TypeError):
            settings = None
        if settings is None:
            await self._reject(send, 503, "API authorization is not configured.")
            return

        token_setting = getattr(settings, "api_token", None) or getattr(
            settings, "coding_api_token", None
        )
        expected = token_setting.get_secret_value() if token_setting else ""
        expires_at = getattr(settings, "api_token_expires_at", None)
        if not expected or len(expected) < 32 or time.time() >= expires_at:
            await self._reject(send, 503, "API authorization is not configured.")
            return

        headers = dict(scope.get("headers", []))
        authorization = headers.get(b"authorization", b"")
        scheme, separator, supplied = authorization.partition(b" ")
        if (
            not separator
            or scheme.lower() != b"bearer"
            or not supplied
            or not hmac.compare_digest(supplied, expected.encode("utf-8"))
        ):
            await self._reject(send, 401, "A valid local API bearer token is required.")
            return

        await self.app(scope, receive, send)

    def _is_public(self, path: str, method: str) -> bool:
        if method == "OPTIONS":
            return True
        if path == f"{self.api_prefix}/health":
            return True
        # OAuth providers return here from an external browser. The callback's
        # one-time state is independently validated by ProductivityService.
        return (
            method == "GET"
            and path.startswith(f"{self.api_prefix}/productivity/oauth/")
            and path.endswith("/callback")
        )

    @staticmethod
    async def _reject(send: Send, status_code: int, detail: str) -> None:
        body = json.dumps({"detail": detail}).encode("utf-8")
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ]
        if status_code == 401:
            headers.append((b"www-authenticate", b"Bearer"))
        await send(
            {"type": "http.response.start", "status": status_code, "headers": headers}
        )
        await send({"type": "http.response.body", "body": body})
