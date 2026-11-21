"""Authorization middleware tests without the Windows socketpair TestClient portal."""

from types import SimpleNamespace

from pydantic import SecretStr

from backend.app.core.api_security import APIAuthorizationMiddleware
from backend.app.core.settings import AppSettings
from backend.app.main import create_app

API_TEST_TOKEN = "test-api-token-for-local-test-client-only-0123456789"


def test_sensitive_api_groups_reject_missing_and_invalid_bearer_tokens() -> None:
    settings = AppSettings(api_token=SecretStr(API_TEST_TOKEN))
    app = create_app(settings)
    assert any(item.cls is APIAuthorizationMiddleware for item in app.user_middleware)
    middleware = APIAuthorizationMiddleware(_downstream, api_prefix=settings.api_prefix)
    application = SimpleNamespace(state=SimpleNamespace(settings=settings))

    protected_paths = (
        ("GET", "/api/v1/settings/user"),
        ("POST", "/api/v1/windows/actions"),
        ("POST", "/api/v1/browser/actions"),
        ("POST", "/api/v1/coding/actions"),
        ("POST", "/api/v1/build/actions"),
        ("POST", "/api/v1/agents/tasks/00000000-0000-0000-0000-000000000001/approve"),
        ("POST", "/api/v1/voice/sessions"),
        ("POST", "/api/v1/documents"),
        ("POST", "/api/v1/plugins/calculator/load"),
        ("GET", "/api/v1/memory"),
        ("GET", "/api/v1/communication/connections"),
    )
    for method, path in protected_paths:
        missing = _invoke(middleware, application, method, path)
        invalid = _invoke(
            middleware,
            application,
            method,
            path,
            authorization="Bearer wrong-token",
        )
        assert _status(missing) == 401
        assert _status(invalid) == 401
    assert (b"www-authenticate", b"Bearer") in missing[0]["headers"]


def test_authorized_request_succeeds_and_health_remains_public() -> None:
    settings = AppSettings(api_token=SecretStr(API_TEST_TOKEN))
    middleware = APIAuthorizationMiddleware(_downstream, api_prefix=settings.api_prefix)
    application = SimpleNamespace(state=SimpleNamespace(settings=settings))

    authorized = _invoke(
        middleware,
        application,
        "GET",
        "/api/v1/settings/user",
        authorization=f"Bearer {API_TEST_TOKEN}",
    )
    public = _invoke(middleware, application, "GET", "/api/v1/health")

    assert _status(authorized) == 200
    assert _status(public) == 200


def test_sensitive_routes_fail_closed_without_server_token() -> None:
    settings = AppSettings()
    middleware = APIAuthorizationMiddleware(_downstream, api_prefix=settings.api_prefix)
    application = SimpleNamespace(state=SimpleNamespace(settings=settings))

    health = _invoke(middleware, application, "GET", "/api/v1/health")
    protected = _invoke(
        middleware,
        application,
        "GET",
        "/api/v1/settings/user",
        authorization=f"Bearer {API_TEST_TOKEN}",
    )

    assert _status(health) == 200
    assert _status(protected) == 503


def test_expired_token_is_rejected() -> None:
    settings = AppSettings(
        api_token=SecretStr(API_TEST_TOKEN), api_token_expires_at=1
    )
    middleware = APIAuthorizationMiddleware(_downstream, api_prefix=settings.api_prefix)
    application = SimpleNamespace(state=SimpleNamespace(settings=settings))

    response = _invoke(
        middleware,
        application,
        "GET",
        "/api/v1/settings/user",
        authorization=f"Bearer {API_TEST_TOKEN}",
    )

    assert _status(response) == 503


async def _downstream(scope, receive, send) -> None:
    del scope, receive
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


async def _receive() -> dict[str, object]:
    return {"type": "http.request", "body": b"", "more_body": False}


async def _collect(messages: list[dict[str, object]], message: dict[str, object]) -> None:
    messages.append(message)


def _invoke(
    middleware: APIAuthorizationMiddleware,
    application: object,
    method: str,
    path: str,
    *,
    authorization: str | None = None,
) -> list[dict[str, object]]:
    headers = []
    if authorization is not None:
        headers.append((b"authorization", authorization.encode("ascii")))
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": headers,
        "app": application,
    }
    messages: list[dict[str, object]] = []
    coroutine = middleware(
        scope,
        _receive,
        lambda message: _collect(messages, message),
    )
    try:
        coroutine.send(None)
    except StopIteration:
        return messages
    finally:
        coroutine.close()
    raise AssertionError("Authorization middleware unexpectedly suspended")


def _status(messages: list[dict[str, object]]) -> int:
    return int(messages[0]["status"])
