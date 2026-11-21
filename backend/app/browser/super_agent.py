"""Safe browser operations exposed through the central capability registry."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from backend.app.capabilities.registry import CapabilityDefinition, CapabilityRegistry
from backend.app.domain.browser import BrowserActionRequest
from backend.app.domain.capability import DevicePlatform, PermissionLevel


class BrowserInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["open", "search", "read", "summarize", "tabs"]
    browser: Literal["system", "chrome", "edge", "firefox"] = "system"
    url: HttpUrl | None = None
    query: str | None = Field(default=None, max_length=500)


class BrowserOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result: dict[str, Any]


class BrowserSuperAgent:
    def register(self, registry: CapabilityRegistry) -> None:
        registry.register(
            CapabilityDefinition.create(
                capability_id="browser.safe_action",
                name="Navigate or inspect browser page",
                description="Open/search a page or inspect the active tab. Form submission and file transfer are excluded.",
                input_model=BrowserInput,
                output_model=BrowserOutput,
                required_permission=PermissionLevel.OPERATE,
                supported_devices=frozenset({DevicePlatform.WINDOWS}),
                handler=self.execute,
                execution_timeout_seconds=60,
            )
        )

    async def execute(self, payload: BrowserInput) -> dict[str, object]:
        if payload.action == "open" and payload.url is None:
            raise ValueError("A URL is required for browser navigation.")
        if payload.action == "search" and not payload.query:
            raise ValueError("A search query is required.")
        if payload.url is not None:
            _assert_public_web_url(str(payload.url))
        from backend.app.api.routes.browser import get_browser_controller

        result = await get_browser_controller().execute(
            BrowserActionRequest(
                action=payload.action,
                browser=payload.browser,
                url=payload.url,
                query=payload.query,
            )
        )
        if not result.success:
            raise RuntimeError("browser_action_failed")
        return {
            "result": {
                "success": result.success,
                "message": result.message,
                "data": result.data,
            }
        }


def _assert_public_web_url(value: str) -> None:
    from ipaddress import ip_address
    from socket import getaddrinfo
    from urllib.parse import urlparse

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only HTTP(S) browser URLs are allowed.")
    host = parsed.hostname.casefold()
    if host == "localhost" or host.endswith(".localhost"):
        raise ValueError("Local browser targets require a separate explicit policy.")
    try:
        addresses = {ip_address(item[4][0]) for item in getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))}
    except OSError as error:
        raise ValueError("The browser host could not be resolved.") from error
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("Private and local network targets are not available through this capability.")
