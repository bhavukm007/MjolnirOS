"""Deterministic decomposition for browser and website commands."""

from __future__ import annotations

from dataclasses import dataclass
import re

from backend.app.browser.website_resolver import WebsiteResolution, WebsiteResolver


_BROWSER_ALIASES = {
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "edge",
    "microsoft edge": "edge",
    "firefox": "firefox",
    "mozilla firefox": "firefox",
}


@dataclass(frozen=True)
class DecomposedBrowserIntent:
    """Independent components of one browser-related command."""

    application: str | None = None
    browser: str | None = None
    website: WebsiteResolution | None = None
    search_query: str | None = None
    sequential_actions: tuple[str, ...] = ()

    @property
    def requires_navigation(self) -> bool:
        return self.website is not None or self.search_query is not None


class IntentDecomposer:
    """Separate browser applications, websites, searches, and action order."""

    def __init__(self, resolver: WebsiteResolver | None = None) -> None:
        self._resolver = resolver or WebsiteResolver()

    def decompose(
        self,
        command: str,
        *,
        preferred_browser: str = "system",
        preferred_email: str = "gmail",
    ) -> DecomposedBrowserIntent | None:
        original = command.strip().rstrip(".,!?")
        normalized = re.sub(r"\s+", " ", original.lower())

        search = re.fullmatch(r"search\s+(?:google\s+)?for\s+(.+)", normalized, re.I)
        if search:
            query = original[search.start(1) : search.end(1)].strip()
            return DecomposedBrowserIntent(
                browser=preferred_browser,
                search_query=query,
                sequential_actions=("launch_browser", "navigate"),
            )

        opened = re.fullmatch(r"open\s+(.+)", original, re.I)
        if not opened:
            return None
        target = opened.group(1).strip()

        combined = re.fullmatch(r"(.+?)\s+and\s+(?:visit|open|go to)\s+(.+)", target, re.I)
        if combined:
            browser = self._browser_name(combined.group(1))
            website = self._resolver.resolve(combined.group(2), preferred_email)
            if browser and website:
                return DecomposedBrowserIntent(
                    application=browser,
                    browser=browser,
                    website=website,
                    sequential_actions=("launch_browser", "wait_for_process", "navigate"),
                )

        in_browser = re.fullmatch(r"(.+?)\s+in\s+(.+)", target, re.I)
        if in_browser:
            browser = self._browser_name(in_browser.group(2))
            website = self._resolver.resolve(in_browser.group(1), preferred_email)
            if browser and website:
                return DecomposedBrowserIntent(
                    application=browser,
                    browser=browser,
                    website=website,
                    sequential_actions=("launch_browser", "wait_for_process", "navigate"),
                )

        browser = self._browser_name(target)
        if browser:
            return DecomposedBrowserIntent(
                application=browser,
                browser=browser,
                sequential_actions=("launch_application",),
            )

        website = self._resolver.resolve(target, preferred_email)
        if website:
            return DecomposedBrowserIntent(
                browser=preferred_browser,
                website=website,
                sequential_actions=("launch_browser", "navigate"),
            )
        if target.lower() in {"email", "mail"} and preferred_email == "mail_app":
            return DecomposedBrowserIntent(
                application="mail",
                sequential_actions=("launch_application",),
            )
        return None

    @staticmethod
    def _browser_name(value: str) -> str | None:
        return _BROWSER_ALIASES.get(re.sub(r"\s+", " ", value.strip().lower()))
