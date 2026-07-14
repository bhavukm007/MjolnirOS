"""Natural-language command recognition for browser and website actions."""

from __future__ import annotations

import logging
from urllib.parse import quote_plus

from backend.app.browser.intent_decomposer import DecomposedBrowserIntent, IntentDecomposer
from backend.app.core.settings import get_settings
from backend.app.domain.browser import BrowserActionRequest
from backend.app.settings.settings_service import SettingsService


logger = logging.getLogger(__name__)


def decompose_browser_command(command: str) -> DecomposedBrowserIntent | None:
    """Decompose a command using persisted, non-secret application preferences."""
    preferences = SettingsService(get_settings()).get()
    intent = IntentDecomposer().decompose(
        command,
        preferred_browser=preferences.preferred_browser,
        preferred_email=preferences.preferred_email_service,
    )
    if intent is not None:
        logger.info(
            "browser_intent_decomposed",
            extra={
                "application": intent.application,
                "browser": intent.browser,
                "website": intent.website.url if intent.website else None,
                "search_query": intent.search_query,
                "sequential_actions": intent.sequential_actions,
            },
        )
    return intent


def parse_browser_command(command: str) -> BrowserActionRequest | None:
    """Translate a decomposed navigation intent into a safe browser request."""
    intent = decompose_browser_command(command)
    if intent is not None and intent.requires_navigation:
        if intent.search_query is not None:
            return BrowserActionRequest(
                action="search",
                browser=intent.browser or "system",
                query=intent.search_query,
                target_label="Google search",
            )
        if intent.website is not None:
            return BrowserActionRequest(
                action="open",
                browser=intent.browser or "system",
                url=intent.website.url,
                target_label=intent.website.name,
            )

    # Retain the established non-navigation Browser Agent commands.
    normalized = command.strip().lower().removeprefix("mjolnir,").strip().rstrip(".,!?")
    if normalized in {"summarize this article", "summarize this page", "summarize"}:
        return BrowserActionRequest(action="summarize")
    if normalized in {"read this article", "read this page", "read page"}:
        return BrowserActionRequest(action="read")
    if normalized == "download the latest python release":
        return BrowserActionRequest(action="open", url="https://www.python.org/downloads/")
    if normalized.startswith("download "):
        target = command[command.lower().find("download ") + 9 :].strip()
        if target.startswith(("http://", "https://")):
            return BrowserActionRequest(action="download", url=target)
    if normalized in {"list tabs", "show tabs"}:
        return BrowserActionRequest(action="tabs")
    if normalized in {"take a screenshot", "screenshot this page"}:
        return BrowserActionRequest(action="screenshot")
    return None


def google_search_url(query: str) -> str:
    """Build a Google search URL without transmitting data anywhere else."""
    return f"https://www.google.com/search?q={quote_plus(query)}"
