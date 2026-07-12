"""Browser Agent safety and behavior tests without live web access."""

from __future__ import annotations

from datetime import UTC, datetime as DateTime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.api.routes import browser
from backend.app.browser import controller as browser_controller
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
        self.clicked = False
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
        self.clicked = True


class FakeDownload:
    """Deterministic Playwright download replacement."""

    def __init__(self, filename: str) -> None:
        self.suggested_filename = filename
        self.saved_path: Path | None = None

    async def save_as(self, path: str) -> None:
        self.saved_path = Path(path)
        self.saved_path.write_bytes(b"downloaded locally")


class FakeDownloadEvent:
    """Async context manager matching Playwright's download event API."""

    def __init__(self, download: FakeDownload) -> None:
        self._download = download

    async def __aenter__(self) -> "FakeDownloadEvent":
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        return None

    @property
    def value(self):
        async def result() -> FakeDownload:
            return self._download
        return result()


class FakePage:
    """Minimal Playwright page replacement."""

    def __init__(self, context: "FakeContext | None" = None, url: str = "about:blank") -> None:
        self._context = context
        self.url = url
        self.body = FakeLocator()
        self.fields: dict[str, FakeLocator] = {}
        self.download = FakeDownload("release.zip")
        self.goto_calls: list[tuple[str, str]] = []
        self.screenshot_calls: list[tuple[Path, bool]] = []

    async def goto(self, url: str, wait_until: str) -> None:
        self.url = url
        self.goto_calls.append((url, wait_until))

    async def title(self) -> str:
        return "Example page"

    def locator(self, selector: str) -> FakeLocator:
        if selector == "body":
            return self.body
        return self.fields.setdefault(selector, FakeLocator())

    def expect_download(self) -> FakeDownloadEvent:
        return FakeDownloadEvent(self.download)

    async def screenshot(self, path: str, full_page: bool) -> None:
        screenshot_path = Path(path)
        screenshot_path.write_bytes(b"png")
        self.screenshot_calls.append((screenshot_path, full_page))

    async def close(self) -> None:
        if self._context is not None:
            self._context.pages.remove(self)


class FakeContext:
    """Minimal persistent-context replacement."""

    def __init__(self, cookies: list[dict[str, str]] | None = None) -> None:
        self.pages = [FakePage(self)]
        self._cookies = cookies if cookies is not None else []
        self.closed = False

    async def new_page(self) -> FakePage:
        page = FakePage(self)
        self.pages.append(page)
        return page

    async def close(self) -> None:
        self.closed = True

    async def add_cookies(self, cookies: list[dict[str, str]]) -> None:
        self._cookies.extend(cookies)

    async def cookies(self) -> list[dict[str, str]]:
        return list(self._cookies)


class FakeSummarizer:
    """Deterministic local summarizer replacement."""

    async def summarize(self, text: str) -> str:
        return f"Summary: {text}"


class FakeBrowserType:
    """Persistent-context launcher with browser-managed profile state."""

    def __init__(self, profiles: dict[str, list[dict[str, str]]]) -> None:
        self._profiles = profiles
        self.launches: list[tuple[str, dict[str, object]]] = []

    async def launch_persistent_context(self, path: str, **options: object) -> FakeContext:
        self.launches.append((path, options))
        return FakeContext(self._profiles.setdefault(path, []))


class FakePlaywright:
    """Playwright type holder used to validate browser selection."""

    def __init__(self, profiles: dict[str, list[dict[str, str]]] | None = None) -> None:
        self.profiles = profiles if profiles is not None else {}
        self.chromium = FakeBrowserType(self.profiles)
        self.firefox = FakeBrowserType(self.profiles)
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True


class FakePlaywrightStarter:
    """Async Playwright starter replacement."""

    def __init__(self, runtime: FakePlaywright) -> None:
        self.runtime = runtime

    async def start(self) -> FakePlaywright:
        return self.runtime


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
async def test_login_handoff_never_handles_credentials_or_security_challenges(tmp_path: Path, monkeypatch, caplog) -> None:
    """Login navigation leaves credentials, MFA, and CAPTCHA entirely to the user."""
    controller = BrowserController(AppSettings(browser_session_path=tmp_path / "sessions"))
    context = FakeContext()

    async def context_for(_: str) -> FakeContext:
        return context

    monkeypatch.setattr(controller, "_context", context_for)
    result = await controller.execute(BrowserActionRequest(action="login", url="https://login.example.test/"))
    password_result = await controller.execute(BrowserActionRequest(action="fill_form", fields={"#password": "super-secret"}))

    assert result.success
    assert context.pages[0].url == "https://login.example.test/"
    assert "Enter credentials" in result.message
    assert "MFA" in result.message and "CAPTCHA" in result.message
    assert result.data == {"url": "https://login.example.test/"}
    assert context.pages[0].fields == {}
    assert "password" not in BrowserActionRequest.model_fields
    assert "credentials" not in BrowserActionRequest.model_fields
    assert not password_result.success
    assert "super-secret" not in password_result.message
    assert "super-secret" not in caplog.text


@pytest.mark.anyio
async def test_screenshot_creates_timestamped_file_and_structured_result(tmp_path: Path, monkeypatch) -> None:
    """A full-page screenshot is persisted with a deterministic timestamped name."""
    screenshot_path = tmp_path / "screenshots"
    controller = BrowserController(AppSettings(browser_session_path=tmp_path / "sessions", browser_screenshot_path=screenshot_path))
    context = FakeContext()

    async def context_for(_: str) -> FakeContext:
        return context

    class FixedDateTime:
        @staticmethod
        def now(timezone):
            return DateTime(2030, 2, 3, 4, 5, 6, tzinfo=UTC)

    monkeypatch.setattr(controller, "_context", context_for)
    monkeypatch.setattr(browser_controller, "datetime", FixedDateTime)
    result = await controller.execute(BrowserActionRequest(action="screenshot"))

    expected_path = screenshot_path / "webpage-20300203040506.png"
    assert result.success
    assert result.message == "Webpage screenshot captured."
    assert result.data == {"path": str(expected_path), "url": "about:blank"}
    assert expected_path.read_bytes() == b"png"
    assert context.pages[0].screenshot_calls == [(expected_path, True)]


@pytest.mark.anyio
async def test_non_executable_download_completes_and_executables_remain_gated(tmp_path: Path, monkeypatch) -> None:
    """Safe downloads save locally while every executable extension needs approval."""
    downloads_path = tmp_path / "downloads"
    controller = BrowserController(AppSettings(browser_session_path=tmp_path / "sessions", browser_download_path=downloads_path))
    context = FakeContext()

    async def context_for(_: str) -> FakeContext:
        return context

    monkeypatch.setattr(controller, "_context", context_for)
    completed = await controller.execute(BrowserActionRequest(action="download", url="https://example.test/release.zip"))

    assert completed.success
    assert completed.message == "Download completed."
    assert completed.data == {"path": str(downloads_path / "release.zip"), "filename": "release.zip"}
    assert (downloads_path / "release.zip").read_bytes() == b"downloaded locally"
    assert context.pages[0].goto_calls[-1] == ("https://example.test/release.zip", "commit")
    for suffix in (".exe", ".msi", ".bat", ".cmd", ".com", ".ps1", ".scr"):
        blocked = await controller.execute(BrowserActionRequest(action="download", url=f"https://example.test/setup{suffix}"))
        assert blocked.confirmation_required is True
        assert blocked.success is False


@pytest.mark.anyio
async def test_normal_form_fields_fill_and_submission_requires_confirmation(tmp_path: Path, monkeypatch) -> None:
    """Ordinary fields fill, password fields reject, and submit remains approval-gated."""
    controller = BrowserController(AppSettings(browser_session_path=tmp_path / "sessions"))
    context = FakeContext()

    async def context_for(_: str) -> FakeContext:
        return context

    monkeypatch.setattr(controller, "_context", context_for)
    filled = await controller.execute(BrowserActionRequest(action="fill_form", fields={"#name": "Ada", "#message": "Hello"}))
    rejected = await controller.execute(BrowserActionRequest(action="fill_form", fields={"#account": "not-a-password", "#password": "secret"}))
    unconfirmed = await controller.execute(BrowserActionRequest(action="submit_form", selector="#send"))
    confirmed = await controller.execute(BrowserActionRequest(action="submit_form", selector="#send", confirmed=True))

    assert filled.success and filled.data == {"field_count": 2}
    assert context.pages[0].fields["#name"].value == "Ada"
    assert context.pages[0].fields["#message"].value == "Hello"
    assert not rejected.success and "secret" not in rejected.message
    assert unconfirmed.confirmation_required is True
    assert confirmed.success
    assert context.pages[0].fields["#send"].clicked is True


@pytest.mark.anyio
async def test_persistent_context_reuses_browser_managed_session_after_restart(tmp_path: Path, monkeypatch) -> None:
    """Controller restarts retain browser-managed session cookies without storing credentials itself."""
    profiles: dict[str, list[dict[str, str]]] = {}
    first_runtime = FakePlaywright(profiles)
    monkeypatch.setattr(browser_controller, "async_playwright", lambda: FakePlaywrightStarter(first_runtime))
    settings = AppSettings(browser_session_path=tmp_path / "sessions", browser_headless=True)
    first_controller = BrowserController(settings)
    first_context = await first_controller._context("chrome")
    await first_context.add_cookies([{"name": "session", "value": "browser-managed-token", "domain": "example.test"}])
    await first_controller.close()

    second_runtime = FakePlaywright(profiles)
    monkeypatch.setattr(browser_controller, "async_playwright", lambda: FakePlaywrightStarter(second_runtime))
    second_controller = BrowserController(settings)
    second_context = await second_controller._context("chrome")

    profile_path = str(settings.browser_session_path / "chrome")
    assert first_context.closed is True
    assert first_runtime.stopped is True
    assert second_context.closed is False
    assert await second_context.cookies() == [{"name": "session", "value": "browser-managed-token", "domain": "example.test"}]
    assert first_runtime.chromium.launches[0][0] == profile_path
    assert second_runtime.chromium.launches[0][0] == profile_path
    assert all("password" not in attribute.lower() and "credential" not in attribute.lower() for attribute in vars(second_controller))
    await second_controller.close()


@pytest.mark.anyio
async def test_complete_tab_lifecycle_keeps_active_tab_consistent(tmp_path: Path, monkeypatch) -> None:
    """Tabs can be created, switched, listed, and closed with a valid active index."""
    controller = BrowserController(AppSettings(browser_session_path=tmp_path / "sessions"))
    context = FakeContext()

    async def context_for(_: str) -> FakeContext:
        return context

    monkeypatch.setattr(controller, "_context", context_for)
    created = await controller.execute(BrowserActionRequest(action="new_tab", url="https://example.test/new"))
    switched = await controller.execute(BrowserActionRequest(action="switch_tab", tab_index=0))
    listed = await controller.execute(BrowserActionRequest(action="tabs"))
    closed = await controller.execute(BrowserActionRequest(action="close_tab", tab_index=0))
    listed_after_close = await controller.execute(BrowserActionRequest(action="tabs"))

    assert created.success and created.data == {"active_tab": 1, "url": "https://example.test/new"}
    assert switched.success and switched.data["active_tab"] == 0
    assert [tab["url"] for tab in listed.data["tabs"]] == ["about:blank", "https://example.test/new"]
    assert closed.success and closed.data["active_tab"] == 0
    assert listed_after_close.data == {"active_tab": 0, "tabs": [{"index": 0, "url": "https://example.test/new"}]}


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
