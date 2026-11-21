"""Regression tests for the Phase 13.0 side-effect execution boundary."""

from time import time
from typing import Any
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from backend.app.ai.capability_router import Capability, CapabilityDecision, CapabilityStatus
from backend.app.api.routes import ai as ai_routes
from backend.app.api.routes import browser, windows
from backend.app.api.routes import build
from backend.app.api.routes import communication, github, productivity
from backend.app.automation.planner_service import PlannerService
from backend.app.domain.ai import ChatRequest
from backend.app.domain.browser import (
    CAPABILITY_BACKED_BROWSER_ACTIONS,
    BrowserActionRequest,
)
from backend.app.domain.build import BuildActionRequest
from backend.app.domain.communication import SendMessageConfirmation
from backend.app.domain.github import GitHubActionRequest, GitHubActionResult
from backend.app.domain.productivity import SendConfirmation
from backend.app.domain.windows import WindowsActionRequest
from backend.app.domain.capability import CapabilityDescriptor, DevicePlatform, PermissionLevel
from backend.app.permissions.engine import ApprovalRequired, PermissionDenied, PermissionEngine
from backend.app.tasks.sqlite_store import SQLiteTaskStore
from backend.app.core.settings import AppSettings
from starlette.requests import Request


def test_system_browser_resolution_reports_unsupported_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import backend.app.browser.controller as browser_controller

    monkeypatch.setattr(browser_controller, "winreg", None)
    with pytest.raises(ValueError, match="only supported on Windows"):
        browser_controller.BrowserController._system_default_browser()


@pytest.mark.parametrize(
    ("program_id", "expected"),
    [
        ("ChromeHTML", "chrome"),
        ("MSEdgeHTM", "edge"),
        ("FirefoxURL", "firefox"),
    ],
)
def test_windows_registry_program_ids_still_resolve(
    monkeypatch: pytest.MonkeyPatch, program_id: str, expected: str
) -> None:
    class RegistryKey:
        def __enter__(self) -> object:
            return self

        def __exit__(self, *_args: object) -> bool:
            return False

    registry = SimpleNamespace(
        HKEY_CURRENT_USER=object(),
        OpenKey=lambda _root, _path: RegistryKey(),
        QueryValueEx=lambda _key, _name: (program_id, 0),
    )
    import backend.app.browser.controller as browser_controller

    monkeypatch.setattr(browser_controller, "winreg", registry)
    assert browser_controller.BrowserController._system_default_browser() == expected


def test_build_route_fails_closed_without_invoking_controller() -> None:
    with pytest.raises(HTTPException) as error:
        _run_immediate(
            build.execute_action(
                BuildActionRequest(action="docker_run", image="x", confirmed=True)
            )
        )

    assert error.value.status_code == 501
    assert "approved agent runtime" in error.value.detail


@pytest.mark.parametrize(
    "action",
    [
        "init",
        "clone",
        "add",
        "commit",
        "push",
        "pull",
        "branch_create",
        "branch_switch",
        "merge",
        "branch_delete",
        "repository_create",
        "issue_create",
        "pull_request_create",
    ],
)
def test_github_mutations_fail_closed_even_with_body_confirmation(
    action: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected_controller() -> object:
        raise AssertionError("mutating GitHub controller must not be invoked")

    monkeypatch.setattr(github, "get_github_controller", unexpected_controller)
    request = GitHubActionRequest(action=action, confirmed=True)
    with pytest.raises(HTTPException) as error:
        _run_immediate(github.execute_action(request))

    assert error.value.status_code == 501
    assert "approved agent runtime" in error.value.detail


@pytest.mark.parametrize("action", ["status", "repository_summary"])
def test_github_read_only_actions_remain_available(
    action: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    class ReadOnlyController:
        async def execute(self, request: GitHubActionRequest) -> GitHubActionResult:
            assert request.action == action
            return GitHubActionResult(success=True, message="read only")

    monkeypatch.setattr(github, "get_github_controller", ReadOnlyController)
    response = _run_immediate(
        github.execute_action(GitHubActionRequest(action=action))
    )

    assert response.success is True
    assert response.message == "read only"


def test_chat_planner_branch_does_not_execute_legacy_planner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MemoryStub:
        def record_conversation(self, _role: str, _content: str) -> None:
            return None

    async def forbidden_execution(self: PlannerService, goal: str) -> str:
        raise AssertionError(f"legacy planner was invoked for {goal!r}")

    monkeypatch.setattr(PlannerService, "execute_goal", forbidden_execution)
    monkeypatch.setattr(ai_routes, "get_memory_store", lambda: object())
    monkeypatch.setattr(ai_routes, "MemoryService", lambda _store: MemoryStub())
    response = _run_immediate(
        ai_routes.stream_chat(
            ChatRequest(message="automate my morning routine"), None  # type: ignore[arg-type]
        )
    )

    first = _run_immediate(response.body_iterator.__anext__())
    second = _run_immediate(response.body_iterator.__anext__())
    third = _run_immediate(response.body_iterator.__anext__())
    _run_immediate(response.body_iterator.aclose())
    assert "Natural-language workflow execution is unavailable" in first + second + third


@pytest.mark.parametrize(
    ("capability", "payload", "expected"),
    [
        (
            Capability.BUILD,
            BuildActionRequest(action="docker_run", image="x", confirmed=True),
            "Build actions are unavailable",
        ),
        (
            Capability.GITHUB,
            GitHubActionRequest(action="push", confirmed=True),
            "Git and GitHub mutations are unavailable",
        ),
    ],
)
def test_chat_build_and_github_mutations_fail_closed(
    capability: Capability,
    payload: object,
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MemoryStub:
        def record_conversation(self, _role: str, _content: str) -> None:
            return None

    decision = CapabilityDecision(
        capability=capability,
        handler="test",
        status=CapabilityStatus.READY,
        reason="test execution boundary",
        confidence=1.0,
        payload=payload,
    )
    monkeypatch.setattr(ai_routes.capability_router, "route", lambda _intent: decision)
    monkeypatch.setattr(ai_routes, "get_memory_store", lambda: object())
    monkeypatch.setattr(ai_routes, "MemoryService", lambda _store: MemoryStub())

    def unexpected_github_controller() -> object:
        raise AssertionError("chat must not invoke a mutating GitHub controller")

    monkeypatch.setattr(github, "get_github_controller", unexpected_github_controller)
    response = _run_immediate(
        ai_routes.stream_chat(ChatRequest(message="test command"), None)  # type: ignore[arg-type]
    )
    body = _stream_body(response)

    assert expected in body


def test_browser_download_and_upload_fail_closed_without_runtime() -> None:
    for action in ("download", "upload"):
        response = _run_immediate(
            browser.execute_browser_action(
                BrowserActionRequest(action=action, url="https://example.com/file"),
                None,  # type: ignore[arg-type]
            )
        )
        assert response.success is False
        assert "not available through the approved capability registry" in response.message


def test_windows_confirmation_flag_cannot_execute_delete(tmp_path) -> None:
    target = tmp_path / "keep.txt"
    target.write_text("preserve", encoding="utf-8")
    settings = AppSettings(
        database_path=tmp_path / "agent.sqlite3",
        windows_search_root=tmp_path,
        coding_project_roots=[tmp_path],
    )
    request = Request(
        {
            "type": "http",
            "headers": [],
            "app": SimpleNamespace(state=SimpleNamespace(settings=settings)),
        }
    )

    response = _run_immediate(
        windows.execute_action(
            WindowsActionRequest(
                action="delete_file",
                arguments={"path": "keep.txt"},
                confirmed=True,
            ),
            request,
        )
    )

    assert response.success is False
    assert response.data.confirmation_required is True
    assert target.read_text(encoding="utf-8") == "preserve"


def test_browser_bookmark_is_not_exposed_as_capability_backed() -> None:
    assert "bookmark" not in CAPABILITY_BACKED_BROWSER_ACTIONS


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/api/v1/communication/drafts/draft-1/send", {"confirmed": True}),
        ("post", "/api/v1/productivity/gmail/drafts/draft-1/send", {"confirmed": True}),
        ("delete", "/api/v1/productivity/drive/files/file-1", {"confirmed": True}),
    ],
)
def test_legacy_confirmation_booleans_do_not_authorize_external_mutations(
    method: str,
    path: str,
    body: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_service() -> object:
        raise AssertionError("confirmation-gated legacy mutation must not execute")

    if path.startswith("/api/v1/communication"):
        monkeypatch.setattr(communication, "_service", unexpected_service)
        with pytest.raises(HTTPException) as error:
            communication.send_draft("draft-1", SendMessageConfirmation(**body))
    else:
        monkeypatch.setattr(productivity, "_service", unexpected_service)
        if method == "post":
            with pytest.raises(HTTPException) as error:
                productivity.send_draft("draft-1", SendConfirmation(**body))
        else:
            with pytest.raises(HTTPException) as error:
                productivity.drive_delete("file-1", SendConfirmation(**body))

    assert error.value.status_code == 501
    assert "unavailable until approval is bound" in error.value.detail


def test_exact_approval_binds_payload_expires_and_is_one_use() -> None:
    engine = PermissionEngine()
    device_id = uuid4()
    scope = "windows.approved_root"
    descriptor = CapabilityDescriptor(
        capability_id="windows.test_write",
        name="Test write",
        description="Test exact approval handling.",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        required_permission=PermissionLevel.MODIFY,
        supported_devices=frozenset({DevicePlatform.WINDOWS}),
        requires_confirmation=True,
    )
    engine.grant(
        device_id=device_id,
        capability_id=descriptor.capability_id,
        permission=PermissionLevel.MODIFY,
        scope=scope,
    )
    payload = {"path": "notes.txt", "content": "approved"}

    with pytest.raises(ApprovalRequired):
        engine.authorize(descriptor, device_id=device_id, scope=scope, payload=payload)

    mismatch = engine.issue_exact_approval(
        device_id=device_id,
        capability_id=descriptor.capability_id,
        scope=scope,
        payload=payload,
    )
    with pytest.raises(PermissionDenied):
        engine.authorize(
            descriptor,
            device_id=device_id,
            scope=scope,
            payload={"path": "other.txt", "content": "approved"},
            approval=mismatch,
        )

    expired = engine.issue_exact_approval(
        device_id=device_id,
        capability_id=descriptor.capability_id,
        scope=scope,
        payload=payload,
    ).model_copy(update={"expires_at": time() - 1})
    with pytest.raises(PermissionDenied):
        engine.authorize(
            descriptor,
            device_id=device_id,
            scope=scope,
            payload=payload,
            approval=expired,
        )

    exact = engine.issue_exact_approval(
        device_id=device_id,
        capability_id=descriptor.capability_id,
        scope=scope,
        payload=payload,
    )
    engine.authorize(
        descriptor,
        device_id=device_id,
        scope=scope,
        payload=payload,
        approval=exact,
    )
    with pytest.raises(PermissionDenied):
        engine.authorize(
            descriptor,
            device_id=device_id,
            scope=scope,
            payload=payload,
            approval=exact,
        )


def test_permission_grant_revocation_survives_ensure(tmp_path) -> None:
    store = SQLiteTaskStore(tmp_path / "agent-test.sqlite3")
    device_id = uuid4()
    grant = store.ensure_permission_grant(
        device_id=device_id,
        capability_id="windows.test_read",
        permission=PermissionLevel.READ,
        scope="windows.approved_root",
    )

    revoked = store.revoke_permission_grant(grant.grant_id)
    after_ensure = store.ensure_permission_grant(
        device_id=device_id,
        capability_id="windows.test_read",
        permission=PermissionLevel.READ,
        scope="windows.approved_root",
    )

    assert revoked.revoked is True
    assert after_ensure.revoked is True
    assert after_ensure.grant_id == grant.grant_id


def _run_immediate(awaitable: Any) -> Any:
    """Drive a route coroutine that must not suspend or perform I/O."""
    if not hasattr(awaitable, "send"):
        raise TypeError("Expected an awaitable coroutine")
    try:
        awaitable.send(None)
    except StopIteration as result:
        return result.value
    finally:
        close = getattr(awaitable, "close", None)
        if close is not None:
            close()
    raise AssertionError("execution-boundary route unexpectedly suspended")


def _stream_body(response: Any) -> str:
    chunks = []
    while True:
        try:
            chunks.append(_run_immediate(response.body_iterator.__anext__()))
        except StopAsyncIteration:
            break
    return "".join(chunks)
