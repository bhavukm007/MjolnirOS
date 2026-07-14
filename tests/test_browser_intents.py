"""Intent decomposition and website resolution coverage."""

from __future__ import annotations

import asyncio

from playwright.async_api import Error as PlaywrightError

from backend.app.browser.controller import BrowserController
from backend.app.browser.intent_decomposer import IntentDecomposer
from backend.app.browser.website_resolver import WebsiteResolver
from backend.app.core.settings import AppSettings
from backend.app.domain.browser import BrowserActionRequest
from backend.app.domain.user_settings import UserSettingsUpdate
from backend.app.settings.settings_service import SettingsService


def test_website_resolver_supports_all_required_aliases() -> None:
    resolver = WebsiteResolver()
    expected = {
        "gmail": "https://mail.google.com/",
        "email": "https://mail.google.com/",
        "mail": "https://mail.google.com/",
        "github": "https://github.com/",
        "gh": "https://github.com/",
        "youtube": "https://www.youtube.com/",
        "yt": "https://www.youtube.com/",
        "chatgpt": "https://chatgpt.com/",
        "gpt": "https://chatgpt.com/",
        "google": "https://www.google.com/",
        "linkedin": "https://www.linkedin.com/",
        "drive": "https://drive.google.com/",
        "calendar": "https://calendar.google.com/",
        "stack overflow": "https://stackoverflow.com/",
    }
    assert {alias: resolver.resolve(alias).url for alias in expected} == expected


def test_resolver_handles_generic_sites_and_search_fallback() -> None:
    decomposer = IntentDecomposer()
    expected = {
        "Open leetcode": "https://leetcode.com",
        "Open chatgpt": "https://chatgpt.com/",
        "Open claude": "https://claude.ai/",
        "Open huggingface": "https://huggingface.co/",
        "Open stackoverflow": "https://stackoverflow.com/",
    }

    for command, url in expected.items():
        intent = decomposer.decompose(command)
        assert intent and intent.website
        assert intent.website.url == url

    unknown = decomposer.decompose("Open some unknown website")
    assert unknown and unknown.website
    assert unknown.website.url == (
        "https://www.google.com/search?q=some+unknown+website"
    )


def test_resolver_does_not_convert_known_applications_into_dot_com_sites() -> None:
    resolver = WebsiteResolver()
    for application in ("Calculator", "Notepad", "Paint", "VS Code", "File Explorer", "Settings"):
        assert resolver.resolve(application) is None


def test_decomposer_separates_websites_browsers_searches_and_sequences() -> None:
    decomposer = IntentDecomposer()

    gmail = decomposer.decompose("Open Gmail")
    assert gmail and gmail.website and gmail.website.url == "https://mail.google.com/"
    assert gmail.browser == "system"

    chrome = decomposer.decompose("Open Google Chrome")
    assert chrome and chrome.application == "chrome" and not chrome.requires_navigation

    combined = decomposer.decompose("Open Chrome and visit github.com")
    assert combined and combined.browser == "chrome"
    assert combined.website and combined.website.url == "https://github.com"
    assert combined.sequential_actions == ("launch_browser", "wait_for_process", "navigate")

    qualified = decomposer.decompose("Open Gmail in Chrome")
    assert qualified and qualified.browser == "chrome"
    assert qualified.website and qualified.website.name == "Gmail"

    search = decomposer.decompose("Search Google for OpenAI GPT-5.5")
    assert search and search.search_query == "OpenAI GPT-5.5"


def test_email_and_browser_preferences_persist_without_memory(tmp_path) -> None:
    settings = AppSettings(settings_storage_directory=tmp_path / "settings")
    service = SettingsService(settings)
    service.update(
        UserSettingsUpdate(preferred_browser="firefox", preferred_email_service="outlook")
    )
    preferences = SettingsService(settings).get()
    intent = IntentDecomposer().decompose(
        "Open Email",
        preferred_browser=preferences.preferred_browser,
        preferred_email=preferences.preferred_email_service,
    )
    assert intent and intent.browser == "firefox"
    assert intent.website and intent.website.url == "https://outlook.live.com/mail/"


def test_controller_launches_context_before_navigation_and_reports_proof(monkeypatch) -> None:
    controller = BrowserController(AppSettings())
    order: list[str] = []

    async def context(_browser):
        order.append("launch")
        controller._resolved_browsers["chrome"] = "chrome"
        return object()

    def page(_context, _browser, _index):
        return object()

    async def opened(_page, url, browser, target_label=None):
        order.append("navigate")
        from backend.app.domain.browser import BrowserActionResult
        return BrowserActionResult(
            success=True,
            message=f"Opened {target_label} in Chrome.",
            data={"browser_started": True, "navigation_succeeded": True, "url": url},
        )

    monkeypatch.setattr(controller, "_context", context)
    monkeypatch.setattr(controller, "_page", page)
    monkeypatch.setattr(controller, "_open", opened)
    result = asyncio.run(
        controller.execute(
            BrowserActionRequest(
                action="open", browser="chrome", url="https://github.com", target_label="GitHub"
            )
        )
    )
    assert order == ["launch", "navigate"]
    assert result.success and result.data["navigation_succeeded"] is True


def test_controller_propagates_navigation_failure(monkeypatch) -> None:
    controller = BrowserController(AppSettings())

    async def context(_browser):
        return object()

    def page(_context, _browser, _index):
        return object()

    async def failed(*_args, **_kwargs):
        raise PlaywrightError("navigation failed")

    monkeypatch.setattr(controller, "_context", context)
    monkeypatch.setattr(controller, "_page", page)
    monkeypatch.setattr(controller, "_open", failed)
    result = asyncio.run(
        controller.execute(BrowserActionRequest(action="open", url="https://github.com"))
    )
    assert result.success is False
    assert "navigation failed" in result.message.lower()
    assert result.data["navigation_succeeded"] is False


def test_controller_keeps_success_when_redirect_invalidates_title_context() -> None:
    controller = BrowserController(AppSettings())
    controller._resolved_browsers["system"] = "chrome"

    class RedirectingPage:
        url = "https://reddit.com"

        def __init__(self):
            self.title_calls = 0
            self.waited_for_final_page = False

        async def goto(self, _url, wait_until):
            assert wait_until == "domcontentloaded"

        async def wait_for_load_state(self, state, timeout):
            assert state == "domcontentloaded"
            assert timeout == 5000
            self.waited_for_final_page = True
            self.url = "https://www.reddit.com/"

        async def title(self):
            self.title_calls += 1
            if self.title_calls == 1:
                raise PlaywrightError("Execution context was destroyed, most likely because of a navigation")
            return "Reddit"

    page = RedirectingPage()
    result = asyncio.run(
        controller._open(page, "https://reddit.com", "system", "Reddit")
    )

    assert result.success is True
    assert result.data["navigation_succeeded"] is True
    assert result.data["url"] == "https://www.reddit.com/"
    assert result.data["title"] == "Reddit"
    assert page.waited_for_final_page is True


def test_controller_falls_back_to_native_navigation_when_playwright_cannot_start(monkeypatch) -> None:
    controller = BrowserController(AppSettings())
    request = BrowserActionRequest(
        action="open",
        browser="chrome",
        url="https://github.com",
        target_label="github.com",
    )

    async def unavailable(_request):
        raise NotImplementedError

    monkeypatch.setattr(controller, "_execute", unavailable)
    monkeypatch.setattr(
        controller,
        "_native_open",
        lambda received: __import__("backend.app.domain.browser", fromlist=["BrowserActionResult"])
        .BrowserActionResult(
            success=True,
            message="Opened github.com in Chrome.",
            data={
                "url": str(received.url),
                "browser_started": True,
                "navigation_succeeded": True,
                "navigation_driver": "native",
            },
        ),
    )

    result = asyncio.run(controller.execute(request))
    assert result.success is True
    assert result.data["navigation_driver"] == "native"
    assert result.data["navigation_succeeded"] is True


def test_controller_falls_back_when_system_browser_resolution_is_unavailable(monkeypatch) -> None:
    controller = BrowserController(AppSettings())
    request = BrowserActionRequest(
        action="open", browser="system", url="https://mail.google.com/", target_label="Gmail"
    )

    async def unavailable(_request):
        raise ValueError("The system default browser could not be resolved.")

    monkeypatch.setattr(controller, "_execute", unavailable)
    monkeypatch.setattr(
        controller,
        "_native_open",
        lambda received: __import__("backend.app.domain.browser", fromlist=["BrowserActionResult"])
        .BrowserActionResult(
            success=True,
            message="Opened Gmail in System.",
            data={"url": str(received.url), "navigation_driver": "native"},
        ),
    )

    result = asyncio.run(controller.execute(request))
    assert result.success is True
    assert result.data["url"] == "https://mail.google.com/"


def test_controller_discards_empty_stale_context_before_relaunch(monkeypatch) -> None:
    controller = BrowserController(AppSettings())

    class StaleContext:
        pages = []

        async def close(self):
            return None

    stale = StaleContext()
    controller._contexts["chrome"] = stale
    controller._active_tabs["chrome"] = 0

    class BrowserType:
        async def launch_persistent_context(self, *_args, **_kwargs):
            return type("FreshContext", (), {"pages": [object()]})()

    async def started():
        return object()

    controller._playwright = awaitable_playwright = type(
        "Playwright", (), {"stop": started}
    )()
    monkeypatch.setattr(
        controller,
        "_launch_options",
        lambda browser: (BrowserType(), {}),
    )
    context = asyncio.run(controller._context("chrome"))
    assert context is not stale
    assert context.pages
