"""Natural-language command recognition for the Browser Agent."""

from __future__ import annotations

from urllib.parse import quote_plus

from backend.app.domain.browser import BrowserActionRequest


_KNOWN_SITES = {
    "gmail": "https://mail.google.com/",
    "google": "https://www.google.com/",
    "github": "https://github.com/",
    "youtube": "https://www.youtube.com/",
}


def parse_browser_command(command: str) -> BrowserActionRequest | None:
    """Translate supported spoken or typed browser commands into safe requests."""
    original = command.strip()
    normalized = original.lower().removeprefix("mjolnir,").strip().rstrip(".,!?")
    if normalized.startswith("search "):
        return BrowserActionRequest(action="search", query=original[original.lower().find("search ") + 7 :].strip())
    if normalized.startswith("open "):
        target = original[original.lower().find("open ") + 5 :].strip()
        clean_target = target.rstrip(".,!?")
        url = _KNOWN_SITES.get(clean_target.lower())
        if url:
            return BrowserActionRequest(action="open", url=url)
        if clean_target.startswith(("http://", "https://")):
            return BrowserActionRequest(action="open", url=clean_target)
        if "." in clean_target and " " not in clean_target:
            return BrowserActionRequest(action="open", url=f"https://{clean_target}")
    if normalized in {"summarize this article", "summarize this page", "summarize"}:
        return BrowserActionRequest(action="summarize")
    if normalized in {"read this article", "read this page", "read page"}:
        return BrowserActionRequest(action="read")
    if normalized == "download the latest python release":
        return BrowserActionRequest(action="open", url="https://www.python.org/downloads/")
    if normalized.startswith("download "):
        target = original[original.lower().find("download ") + 9 :].strip()
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
