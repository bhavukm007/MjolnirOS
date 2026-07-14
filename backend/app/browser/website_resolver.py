"""Centralized, extensible website alias resolution."""

from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import quote_plus, urlparse


@dataclass(frozen=True)
class WebsiteResolution:
    """A canonical website target produced from a user-facing alias."""

    name: str
    url: str


class WebsiteResolver:
    """Resolve website aliases without spreading URL constants across handlers."""

    DEFAULT_SITES: dict[str, tuple[str, tuple[str, ...]]] = {
        "Gmail": ("https://mail.google.com/", ("gmail", "email", "mail")),
        "GitHub": ("https://github.com/", ("github", "gh")),
        "YouTube": ("https://www.youtube.com/", ("youtube", "yt")),
        "ChatGPT": ("https://chatgpt.com/", ("chatgpt", "chat gpt", "gpt")),
        # Canonical non-.com destinations remain aliases; ordinary one-word
        # site names are handled generically below.
        "Claude": ("https://claude.ai/", ("claude",)),
        "Hugging Face": ("https://huggingface.co/", ("huggingface", "hugging face")),
        "Stack Overflow": ("https://stackoverflow.com/", ("stackoverflow", "stack overflow")),
        "Google": ("https://www.google.com/", ("google",)),
        "LinkedIn": ("https://www.linkedin.com/", ("linkedin", "linked in")),
        "Google Drive": ("https://drive.google.com/", ("drive", "google drive")),
        "Google Calendar": ("https://calendar.google.com/", ("calendar", "google calendar")),
        "Outlook": ("https://outlook.live.com/mail/", ("outlook", "outlook mail")),
    }

    _APPLICATION_TARGETS = {
        "chrome",
        "google chrome",
        "edge",
        "microsoft edge",
        "calculator",
        "calc",
        "notepad",
        "paint",
        "vs code",
        "visual studio code",
        "vscode",
        "file explorer",
        "explorer",
        "settings",
    }

    def __init__(self, sites: dict[str, tuple[str, tuple[str, ...]]] | None = None) -> None:
        self._sites = sites or self.DEFAULT_SITES
        self._aliases = {
            self._normalize(alias): WebsiteResolution(name=name, url=url)
            for name, (url, aliases) in self._sites.items()
            for alias in aliases
        }

    def resolve(self, target: str, preferred_email: str = "gmail") -> WebsiteResolution | None:
        """Resolve an alias or explicit host/URL to a canonical HTTPS URL."""
        normalized = self._normalize(target)
        if normalized in {"email", "mail"}:
            if preferred_email == "outlook":
                return self._aliases["outlook"]
            if preferred_email == "mail_app":
                return None
        resolution = self._aliases.get(normalized)
        if resolution is not None:
            return resolution
        if normalized in self._APPLICATION_TARGETS:
            return None

        candidate = target.strip().rstrip(".,!?")
        if candidate.startswith(("http://", "https://")):
            parsed = urlparse(candidate)
            return WebsiteResolution(name=parsed.hostname or candidate, url=candidate)
        if re.fullmatch(r"(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s]*)?", candidate, re.I):
            host = candidate.split("/", 1)[0]
            return WebsiteResolution(name=host, url=f"https://{candidate}")

        # A simple brand-like token is a confident conventional website name.
        # This covers new sites without requiring an alias for every .com host.
        if re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", candidate, re.I):
            host = f"{candidate.lower()}.com"
            return WebsiteResolution(name=candidate, url=f"https://{host}")

        # Explicitly website-shaped but ambiguous phrases stay in the browser
        # path and degrade safely to a search instead of application launch.
        if re.search(r"\b(?:website|site|webpage|web page)\b", normalized):
            return WebsiteResolution(
                name=f"Google search for {candidate}",
                url=f"https://www.google.com/search?q={quote_plus(candidate)}",
            )
        return None

    def is_alias(self, target: str) -> bool:
        return self._normalize(target) in self._aliases

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip().lower().rstrip(".,!?"))
