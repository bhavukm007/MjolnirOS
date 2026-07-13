"""Playwright-backed, local-first browser automation controller."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import BrowserContext, Error as PlaywrightError, Page, Playwright, async_playwright

from backend.app.browser.natural_language import google_search_url
from backend.app.browser.summarizer import PageSummarizer
from backend.app.core.settings import AppSettings
from backend.app.domain.browser import BrowserActionRequest, BrowserActionResult, BrowserName


_EXECUTABLE_SUFFIXES = {".exe", ".msi", ".bat", ".cmd", ".com", ".ps1", ".scr"}


class BrowserController:
    """Manage persistent Playwright contexts without handling user credentials."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._playwright: Playwright | None = None
        self._contexts: dict[BrowserName, BrowserContext] = {}
        self._active_tabs: dict[BrowserName, int] = {}
        self._lock = asyncio.Lock()
        self._summarizer = PageSummarizer(settings)
        self._logger = logging.getLogger(__name__)

    async def execute(self, request: BrowserActionRequest) -> BrowserActionResult:
        """Perform one browser action and always return a structured outcome."""
        if self._requires_confirmation(request):
            return BrowserActionResult(
                success=False,
                message="Confirmation is required before this browser action.",
                confirmation_required=True,
            )
        try:
            return await self._execute(request)
        except (PlaywrightError, OSError, ValueError) as error:
            self._logger.warning(
                "browser_action_failed",
                extra={"action": request.action, "browser": request.browser, "error_type": type(error).__name__},
            )
            return BrowserActionResult(success=False, message="Browser action failed. Check the browser session and request.")

    async def close(self) -> None:
        """Release running browser contexts while retaining their local sessions."""
        for context in self._contexts.values():
            await context.close()
        self._contexts.clear()
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def _execute(self, request: BrowserActionRequest) -> BrowserActionResult:
        context = await self._context(request.browser)
        page = self._page(context, request.browser, request.tab_index)
        if request.action == "open":
            return await self._open(page, self._required_url(request))
        if request.action == "new_tab":
            return await self._new_tab(context, request.browser, request.url)
        if request.action == "search":
            if not request.query:
                raise ValueError("A search query is required.")
            return await self._open(page, google_search_url(request.query), message="Google search opened.")
        if request.action == "read":
            return await self._read(page)
        if request.action == "summarize":
            return await self._summarize(page)
        if request.action == "download":
            return await self._download(page, self._required_url(request))
        if request.action == "upload":
            return await self._upload(page, request)
        if request.action == "fill_form":
            return await self._fill_form(page, request.fields)
        if request.action == "submit_form":
            return await self._submit_form(page, request.selector)
        if request.action == "login":
            return await self._login(page, request.url)
        if request.action == "tabs":
            return self._tabs(context, request.browser)
        if request.action == "switch_tab":
            return self._switch_tab(context, request.browser, request.tab_index)
        if request.action == "close_tab":
            return await self._close_tab(context, request.browser, request.tab_index)
        if request.action == "bookmark":
            return self._bookmark(page)
        if request.action == "screenshot":
            return await self._screenshot(page)
        raise ValueError("Unsupported browser action.")

    async def _context(self, browser: BrowserName) -> BrowserContext:
        async with self._lock:
            if browser in self._contexts:
                return self._contexts[browser]
            session_path = self._settings.browser_session_path / browser
            session_path.mkdir(parents=True, exist_ok=True)
            os.chmod(session_path, 0o700)
            if self._playwright is None:
                self._playwright = await async_playwright().start()
            browser_type, launch_options = self._launch_options(browser)
            context = await browser_type.launch_persistent_context(
                str(session_path),
                headless=self._settings.browser_headless,
                accept_downloads=True,
                **launch_options,
            )
            self._contexts[browser] = context
            self._active_tabs[browser] = 0
            self._logger.info("browser_session_started", extra={"browser": browser})
            return context

    def _launch_options(self, browser: BrowserName) -> tuple[Any, dict[str, str]]:
        if self._playwright is None:
            raise RuntimeError("Playwright was not initialized.")
        if browser == "chrome":
            return self._playwright.chromium, {"channel": "chrome"}
        if browser == "edge":
            return self._playwright.chromium, {"channel": "msedge"}
        return self._playwright.firefox, {}

    def _page(self, context: BrowserContext, browser: BrowserName, tab_index: int | None) -> Page:
        pages = context.pages
        if not pages:
            raise ValueError("The browser has no open tabs.")
        index = tab_index if tab_index is not None else self._active_tabs.get(browser, 0)
        if index >= len(pages):
            raise ValueError("The requested tab does not exist.")
        self._active_tabs[browser] = index
        return pages[index]

    async def _open(self, page: Page, url: str, message: str = "Website opened.") -> BrowserActionResult:
        await page.goto(url, wait_until="domcontentloaded")
        return BrowserActionResult(success=True, message=message, data={"url": page.url, "title": await page.title()})

    async def _read(self, page: Page) -> BrowserActionResult:
        text = (await page.locator("body").inner_text()).strip()
        return BrowserActionResult(success=True, message="Page read.", data={"url": page.url, "title": await page.title(), "content": text[:100_000]})

    async def _summarize(self, page: Page) -> BrowserActionResult:
        text = (await page.locator("body").inner_text()).strip()
        summary = await self._summarizer.summarize(text)
        return BrowserActionResult(success=True, message="Page summarized locally.", data={"url": page.url, "title": await page.title(), "summary": summary})

    async def _new_tab(self, context: BrowserContext, browser: BrowserName, url: Any) -> BrowserActionResult:
        page = await context.new_page()
        self._active_tabs[browser] = len(context.pages) - 1
        if url is not None:
            await page.goto(str(url), wait_until="domcontentloaded")
        return BrowserActionResult(success=True, message="New tab opened.", data={"active_tab": self._active_tabs[browser], "url": page.url})

    async def _download(self, page: Page, url: str) -> BrowserActionResult:
        self._settings.browser_download_path.mkdir(parents=True, exist_ok=True)
        async with page.expect_download() as event:
            await page.goto(url, wait_until="commit")
        download = await event.value
        filename = download.suggested_filename
        path = self._settings.browser_download_path / filename
        await download.save_as(str(path))
        return BrowserActionResult(success=True, message="Download completed.", data={"path": str(path), "filename": filename})

    async def _upload(self, page: Page, request: BrowserActionRequest) -> BrowserActionResult:
        if not request.selector or not request.file_path:
            raise ValueError("A file selector and local file path are required for upload.")
        file_path = Path(request.file_path).expanduser().resolve()
        if not file_path.is_file():
            raise ValueError("The upload file does not exist.")
        await page.locator(request.selector).set_input_files(str(file_path))
        return BrowserActionResult(success=True, message="File selected for upload. Submit remains pending confirmation.", data={"path": str(file_path)})

    async def _fill_form(self, page: Page, fields: dict[str, str]) -> BrowserActionResult:
        if not fields:
            raise ValueError("At least one form field is required.")
        for selector, value in fields.items():
            if any(marker in selector.lower() for marker in ("password", "passcode", "pwd")):
                raise ValueError("Credential automation is prohibited.")
            locator = page.locator(selector)
            input_type = (await locator.get_attribute("type") or "").lower()
            if input_type == "password":
                raise ValueError("Credential automation is prohibited.")
            await locator.fill(value)
        return BrowserActionResult(success=True, message="Form fields filled. Submission requires confirmation.", data={"field_count": len(fields)})

    async def _submit_form(self, page: Page, selector: str | None) -> BrowserActionResult:
        await page.locator(selector or "form button[type='submit'], form input[type='submit']").first.click()
        return BrowserActionResult(success=True, message="Form submitted.")

    async def _login(self, page: Page, url: Any) -> BrowserActionResult:
        if url is not None:
            await page.goto(str(url), wait_until="domcontentloaded")
        return BrowserActionResult(success=True, message="Login page is ready. Enter credentials and complete MFA or CAPTCHA directly in the browser.", data={"url": page.url})

    def _tabs(self, context: BrowserContext, browser: BrowserName) -> BrowserActionResult:
        return BrowserActionResult(success=True, message="Tabs listed.", data={"active_tab": self._active_tabs.get(browser, 0), "tabs": [{"index": index, "url": page.url} for index, page in enumerate(context.pages)]})

    def _switch_tab(self, context: BrowserContext, browser: BrowserName, tab_index: int | None) -> BrowserActionResult:
        if tab_index is None or tab_index >= len(context.pages):
            raise ValueError("A valid tab index is required.")
        self._active_tabs[browser] = tab_index
        return BrowserActionResult(success=True, message="Active tab changed.", data={"active_tab": tab_index, "url": context.pages[tab_index].url})

    async def _close_tab(self, context: BrowserContext, browser: BrowserName, tab_index: int | None) -> BrowserActionResult:
        index = tab_index if tab_index is not None else self._active_tabs.get(browser, 0)
        if len(context.pages) <= 1:
            raise ValueError("The last browser tab cannot be closed.")
        if index >= len(context.pages):
            raise ValueError("The requested tab does not exist.")
        await context.pages[index].close()
        self._active_tabs[browser] = min(index, len(context.pages) - 1)
        return BrowserActionResult(success=True, message="Tab closed.", data={"active_tab": self._active_tabs[browser]})

    def _bookmark(self, page: Page) -> BrowserActionResult:
        return BrowserActionResult(success=True, message="Page is ready to save as a local bookmark.", data={"url": page.url})

    async def _screenshot(self, page: Page) -> BrowserActionResult:
        self._settings.browser_screenshot_path.mkdir(parents=True, exist_ok=True)
        path = self._settings.browser_screenshot_path / f"webpage-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.png"
        await page.screenshot(path=str(path), full_page=True)
        return BrowserActionResult(success=True, message="Webpage screenshot captured.", data={"path": str(path), "url": page.url})

    @staticmethod
    def _required_url(request: BrowserActionRequest) -> str:
        if request.url is None:
            raise ValueError("A website URL is required.")
        return str(request.url)

    @staticmethod
    def _requires_confirmation(request: BrowserActionRequest) -> bool:
        if request.action == "submit_form":
            return not request.confirmed
        if request.action != "download" or request.url is None:
            return False
        suffix = Path(urlparse(str(request.url)).path).suffix.lower()
        return suffix in _EXECUTABLE_SUFFIXES and not request.confirmed
