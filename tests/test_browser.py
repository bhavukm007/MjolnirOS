"""Browser Agent safety and behavior tests without live web access."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.api.routes import browser
from backend.app.browser.controller import BrowserController
from backend.app.browser.natural_language import parse_browser_command
from backend.app.core.settings import AppSettings
from backend.app.domain.browser import BrowserActionRequest, BrowserActionResult
from backend.app.main import create_app


class FakeLocator:
    """Minimal Playwright locator replacement."""

    def __init__(self, text: str = "A first sentence. A second sentence.", input_type: str = "text") -> None:
        self._text = text
        self._input_type = input_type
        self.value = ""
        self.files = ""
        self.first = self

    async def inner_text(self) -> str:
        return self._text

    async def get_attribute(self, name: str) -> str | None:
        return self._input_type if name == "type" else None

    async def fill(self, value: str) -> None:
        self.value = value

    async def set_input_files(self, path: str) -> None:
        self.files = path

    async def click(self) -> None:
        return None


class FakePage:
    """Minimal Playwright page replacement."""

    def __init__(self, url: str = "about:blank") -> None:
        self.url = url
        self.body = FakeLocator()
        self.fields: dict[str, FakeLocator] = {}

    async def goto(self, url: str, wait_until: str) -> None:
        self.url = url

    async def title(self) -> str:
        return "Example page"

    def locator(self, selector: str) -> FakeLocator:
        if selector == "body":
            return self.body
        return self.fields.setdefault(selector, FakeLocator())


class FakeContext:
    """Minimal persistent-context replacement."""

    def __init__(self) -> None:
        self.pages = [FakePage()]


class FakeSummarizer:
    """Deterministic local summarizer replacement."""

    async def summarize(self, text: str) -> str:
        return f"Summary: {text}"


class FakePlaywright:
    """Playwright type holder used to validate browser selection."""

    chromium = object()
    firefox = object()


@pytest.mark.anyio
async def test_search_read_summary_and_upload_are_structured(tmp_path: Path, monkeypatch) -> None:
    """Core non-destructive actions use the Playwright layer and return data."""
    controller = BrowserController(AppSettings(browser_session_path=tmp_path / "sessions"))
    context = FakeContext()
    controller._summarizer = FakeSummarizer()

    async def context_for(_: str) -> FakeContext:
        return context

    monkeypatch.setattr(controller, "_context", context_for)
    searched = await controller.execute(BrowserActionRequest(action="search", query="GitHub Copilot"))
    read = await controller.execute(BrowserActionRequest(action="read"))
    summary = await controller.execute(BrowserActionRequest(action="summarize"))
    upload_path = tmp_path / "note.txt"
    upload_path.write_text("local", encoding="utf-8")
    uploaded = await controller.execute(BrowserActionRequest(action="upload", selector="#file", file_path=str(upload_path)))

    assert searched.success and "google.com/search" in searched.data["url"]
    assert read.success and "A first sentence" in read.data["content"]
    assert summary.data["summary"].startswith("Summary:")
    assert uploaded.success and context.pages[0].fields["#file"].files == str(upload_path.resolve())


@pytest.mark.anyio
async def test_tabs_and_password_safety(tmp_path: Path, monkeypatch) -> None:
    """Tabs work while password inputs are never filled or returned."""
    controller = BrowserController(AppSettings(browser_session_path=tmp_path / "sessions"))
    context = FakeContext()

    async def context_for(_: str) -> FakeContext:
        return context

    monkeypatch.setattr(controller, "_context", context_for)
    context.pages[0].fields["#password"] = FakeLocator(input_type="password")
    rejected = await controller.execute(BrowserActionRequest(action="fill_form", fields={"#password": "secret"}))
    tabs = await controller.execute(BrowserActionRequest(action="tabs"))

    assert not rejected.success
    assert "secret" not in rejected.message
    assert tabs.success and tabs.data["active_tab"] == 0


@pytest.mark.anyio
async def test_submission_and_executable_download_require_confirmation(tmp_path: Path) -> None:
    """Sensitive browser effects are stopped before a context is launched."""
    controller = BrowserController(AppSettings(browser_session_path=tmp_path / "sessions"))
    submit = await controller.execute(BrowserActionRequest(action="submit_form"))
    executable = await controller.execute(BrowserActionRequest(action="download", url="https://example.test/setup.exe"))

    assert submit.confirmation_required is True
    assert executable.confirmation_required is True


def test_chrome_edge_and_firefox_use_the_supported_playwright_targets(tmp_path: Path) -> None:
    """Each supported browser maps to its Playwright launcher and channel."""
    controller = BrowserController(AppSettings(browser_session_path=tmp_path / "sessions"))
    controller._playwright = FakePlaywright()

    chrome_type, chrome_options = controller._launch_options("chrome")
    edge_type, edge_options = controller._launch_options("edge")
    firefox_type, firefox_options = controller._launch_options("firefox")

    assert chrome_type is controller._playwright.chromium and chrome_options == {"channel": "chrome"}
    assert edge_type is controller._playwright.chromium and edge_options == {"channel": "msedge"}
    assert firefox_type is controller._playwright.firefox and firefox_options == {}


def test_natural_language_routes_browser_commands() -> None:
    """Voice and text command phrases map to safe browser actions."""
    search = parse_browser_command("Mjolnir, search GitHub Copilot.")
    gmail = parse_browser_command("Mjolnir, open Gmail.")
    summary = parse_browser_command("Mjolnir, summarize this article.")

    assert search and search.action == "search" and search.query == "GitHub Copilot."
    assert gmail and str(gmail.url) == "https://mail.google.com/"
    assert summary and summary.action == "summarize"


def test_browser_route_persists_bookmarks_without_sensitive_data(monkeypatch) -> None:
    """Bookmarks are sent to the existing local Memory System."""
    class Controller:
        async def execute(self, request: BrowserActionRequest) -> BrowserActionResult:
            return BrowserActionResult(success=True, message="Page is ready to save as a local bookmark.", data={"url": "https://example.test/"})

    class MemoryStore:
        def __init__(self) -> None:
            self.memory = None

        def save(self, memory):
            self.memory = memory

    store = MemoryStore()
    monkeypatch.setattr(browser, "get_browser_controller", lambda: Controller())
    monkeypatch.setattr(browser, "get_memory_store", lambda: store)
    response = TestClient(create_app()).post("/api/v1/browser/actions", json={"action": "bookmark"})

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert store.memory.memory_type == "bookmark"
