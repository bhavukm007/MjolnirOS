"""Linux HTTP integration coverage for the Phase 13.0 execution boundary."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from backend.app.core.settings import AppSettings


pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(
        sys.platform == "win32",
        reason="Windows asyncio socketpair fallback blocks before ASGI dispatch.",
    ),
]
TOKEN = "phase-13-http-test-token-0123456789abcdef"


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
async def asgi_client(tmp_path_factory):
    from backend.app.main import create_app

    root = tmp_path_factory.mktemp("phase13-http")
    settings = AppSettings(
        environment="test",
        api_token=SecretStr(TOKEN),
        log_file=str(root / "logs" / "test.log"),
        database_path=root / "agent.sqlite3",
        windows_search_root=root.parent,
        coding_project_roots=[root.parent],
        browser_session_path=root / "browser",
        plugin_directory=root / "plugins",
        plugin_catalog_file=root / "plugins" / "catalog.json",
        plugin_state_file=root / "plugin-state.json",
        settings_storage_directory=root / "settings",
        automation_storage_directory=root / "automation",
        learning_storage_directory=root / "learning",
        productivity_storage_directory=root / "productivity",
        communication_storage_directory=root / "communication",
        audit_storage_directory=root / "audit",
        vision_upload_directory=root / "documents",
        chroma_path=root / "chroma",
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            client.phase13_test_root = root.parent
            yield client


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


async def test_http_authentication_health_and_build_fail_closed(asgi_client):
    public = await asgi_client.get("/api/v1/health")
    missing = await asgi_client.get("/api/v1/agents/capabilities")
    invalid = await asgi_client.get(
        "/api/v1/agents/capabilities",
        headers={"Authorization": "Bearer invalid"},
    )
    valid = await asgi_client.get(
        "/api/v1/agents/capabilities", headers=_headers()
    )
    unauthorized_build = await asgi_client.post(
        "/api/v1/build/actions",
        json={"action": "docker_run", "confirmed": True},
    )
    build = await asgi_client.post(
        "/api/v1/build/actions",
        headers=_headers(),
        json={"action": "docker_run", "confirmed": True},
    )

    assert public.status_code == 200
    assert missing.status_code == invalid.status_code == 401
    assert valid.status_code == 200
    assert unauthorized_build.status_code == 401
    assert build.status_code == 501


async def test_http_github_read_only_and_mutations_fail_closed(asgi_client, monkeypatch):
    from backend.app.api.routes import github
    from backend.app.domain.github import GitHubActionResult

    class ReadOnlyController:
        async def execute(self, request):
            assert request.action in {"status", "repository_summary"}
            return GitHubActionResult(success=True, message="read-only result")

    monkeypatch.setattr(github, "get_github_controller", ReadOnlyController)
    status = await asgi_client.post(
        "/api/v1/github/actions",
        headers=_headers(),
        json={"action": "status"},
    )
    summary = await asgi_client.post(
        "/api/v1/github/actions",
        headers=_headers(),
        json={"action": "repository_summary"},
    )
    mutation = await asgi_client.post(
        "/api/v1/github/actions",
        headers=_headers(),
        json={"action": "push", "confirmed": True},
    )

    assert status.status_code == summary.status_code == 200
    assert mutation.status_code == 501


async def test_http_communication_and_productivity_sends_are_disabled(
    asgi_client, monkeypatch
):
    from backend.app.api.routes import communication, productivity
    from backend.app.domain.communication import MessageDraft

    draft = MessageDraft(
        id="draft-1",
        provider="slack",
        conversation_id="conversation-1",
        content="Draft only",
        status="draft",
        created_at="2026-01-01T00:00:00Z",
    )

    class DraftService:
        def create_draft(self, _provider, _payload):
            return draft

    monkeypatch.setattr(communication, "_service", DraftService)
    comm_draft = await asgi_client.post(
        "/api/v1/communication/slack/drafts",
        headers=_headers(),
        json={"conversation_id": "conversation-1", "content": "Draft only"},
    )
    comm_send = await asgi_client.post(
        "/api/v1/communication/drafts/draft-1/send",
        headers=_headers(),
        json={"confirmed": True},
    )
    email_send = await asgi_client.post(
        "/api/v1/productivity/gmail/drafts/draft-1/send",
        headers=_headers(),
        json={"confirmed": True},
    )
    drive_delete = await asgi_client.request(
        "DELETE",
        "/api/v1/productivity/drive/files/file-1",
        headers=_headers(),
        json={"confirmed": True},
    )

    assert comm_draft.status_code == 201
    assert comm_draft.json()["data"]["status"] == "draft"
    assert comm_send.status_code == email_send.status_code == drive_delete.status_code == 501


@pytest.mark.parametrize("action", ["bookmark", "download", "upload"])
async def test_http_unsupported_browser_actions_fail_closed(asgi_client, action):
    response = await asgi_client.post(
        "/api/v1/browser/actions",
        headers=_headers(),
        json={"action": action, "url": "https://example.com"},
    )
    assert response.status_code == 200
    assert response.json()["success"] is False


async def test_browser_route_imports_and_system_browser_fails_clearly_on_linux():
    from backend.app.api.routes import browser as browser_routes
    from backend.app.browser.controller import BrowserController
    from backend.app.domain.browser import BrowserActionRequest

    assert browser_routes.router is not None
    result = await BrowserController(AppSettings()).execute(
        BrowserActionRequest(
            action="open", browser="system", url="https://example.com"
        )
    )

    assert result.success is False
    assert "only supported on windows" in result.message.lower()
    assert result.data["error_type"] == "ValueError"


async def test_http_windows_sensitive_action_requires_exact_runtime_approval(
    asgi_client
):
    target = asgi_client.phase13_test_root / ".phase13-http-preserve.txt"
    target.write_text("keep", encoding="utf-8")
    response = await asgi_client.post(
        "/api/v1/windows/actions",
        headers=_headers(),
        json={
            "action": "delete_file",
            "arguments": {"path": str(target)},
            "confirmed": True,
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["confirmation_required"] is True
    assert target.read_text(encoding="utf-8") == "keep"


async def test_http_coding_capability_and_approval_boundary(asgi_client, tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    read = await asgi_client.post(
        "/api/v1/coding/actions",
        headers=_headers(),
        json={"action": "list_projects"},
    )
    sensitive = await asgi_client.post(
        "/api/v1/coding/actions",
        headers=_headers(),
        json={"action": "run_command", "command": "flask run", "cwd": str(project)},
    )
    assert read.status_code == 200
    assert read.json()["success"] is True
    assert sensitive.status_code == 200
    assert sensitive.json()["data"]["confirmation_required"] is True


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("build docker image", "Build actions are unavailable"),
        ("push my project", "Git and GitHub mutations are unavailable"),
        ("automate my morning routine", "Natural-language workflow execution is unavailable"),
    ],
)
async def test_http_chat_restricted_requests_fail_closed(
    asgi_client, monkeypatch, message, expected
):
    from backend.app.api.routes import ai, github

    class MemoryStub:
        def record_conversation(self, _role, _content):
            return None

    monkeypatch.setattr(ai, "get_memory_store", lambda: object())
    monkeypatch.setattr(ai, "MemoryService", lambda _store: MemoryStub())
    monkeypatch.setattr(
        github,
        "get_github_controller",
        lambda: (_ for _ in ()).throw(AssertionError("mutating chat invoked GitHub controller")),
    )
    response = await asgi_client.post(
        "/api/v1/chat",
        headers=_headers(),
        json={"message": message},
    )
    assert response.status_code == 200
    assert expected in response.text
