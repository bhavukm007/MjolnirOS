"""Schemas for safe local browser automation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


BrowserName = Literal["system", "chrome", "edge", "firefox"]
BrowserActionName = Literal[
    "open",
    "new_tab",
    "search",
    "read",
    "summarize",
    "download",
    "upload",
    "fill_form",
    "submit_form",
    "login",
    "tabs",
    "switch_tab",
    "close_tab",
    "bookmark",
    "screenshot",
]


class BrowserActionRequest(BaseModel):
    """A browser action request that never accepts credentials."""

    action: BrowserActionName = "open"
    browser: BrowserName = "system"
    url: HttpUrl | None = None
    query: str | None = Field(default=None, max_length=500)
    selector: str | None = Field(default=None, max_length=1000)
    fields: dict[str, str] = Field(default_factory=dict)
    file_path: str | None = Field(default=None, max_length=4096)
    tab_index: int | None = Field(default=None, ge=0)
    confirmed: bool = False
    target_label: str | None = Field(default=None, max_length=200)

class BrowserActionResult(BaseModel):
    """Structured, password-safe result for every browser action."""

    success: bool
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    confirmation_required: bool = False
