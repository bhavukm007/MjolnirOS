"""Authentication helpers for privileged local coding operations."""

from __future__ import annotations

import hmac
import time

from fastapi import HTTPException, Request, status


def assert_coding_authorized(request: Request) -> None:
    """Keep explicit authorization on shell-capable code paths as defense in depth."""
    settings = request.app.state.settings
    configured_token = settings.api_token or settings.coding_api_token
    if (
        configured_token is None
        or len(configured_token.get_secret_value()) < 32
        or time.time() >= settings.api_token_expires_at
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Privileged coding operations are disabled because API authorization is not configured.",
        )
    # The application-wide middleware validates the token; this dependency also
    # prevents direct invocation of the route dependency from being permissive.
    expected = configured_token.get_secret_value()
    supplied = request.headers.get("authorization", "")
    scheme, separator, value = supplied.partition(" ")
    if (
        not separator
        or scheme.lower() != "bearer"
        or not hmac.compare_digest(value, expected)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid local API bearer token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
