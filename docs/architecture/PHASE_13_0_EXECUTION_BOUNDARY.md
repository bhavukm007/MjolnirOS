# Phase 13.0 Execution Boundary

## Scope

This phase closes direct chat and API dispatch paths that could perform local
build work, Git/GitHub mutations, or natural-language multi-controller
execution without `AgentRuntime` authorization. It does not add planning,
durability, recovery, or new capabilities.

## Enforced paths

- `/api/v1/agents/tasks` remains the execution boundary for registered
  capabilities: `AgentRuntime` validates registration and persists the task;
  `CapabilityRegistry` validates typed input/device and calls
  `PermissionEngine` before invoking a handler.
- `/api/v1/windows/actions`, `/api/v1/browser/actions`, and
  `/api/v1/coding/actions` continue to adapt supported requests into registered
  agent tasks. Unsupported actions fail closed.
- Browser `bookmark` was removed from the allowed action list because it wrote
  local memory after capability execution, outside the registry path.
- Legacy email/message send and Google Drive delete routes now return explicit
  501 responses. Their `confirmed` body field was not independent approval.
- `/api/v1/build/actions` and the Build chat branch now return an explicit 501
  unsupported response. There is no registered build capability to safely
  adapt the existing build controller.
- `/api/v1/github/actions` and the GitHub chat branch permit only `status` and
  `repository_summary`. Git and GitHub mutations return an explicit 501 until
  registered capability handlers and exact-action approval are available.
- Natural-language chat no longer invokes `PlannerService.execute_goal`.
  That method now returns an explicit unavailable response; `/automation/plans`
  remains a descriptive plan API and `/automation/workflows` remains a separate
  notification/wait workflow facility.

## Authorization and known limitations

All non-public API routes remain protected by the configured bearer-token
middleware. `/health`, CORS preflight, and the productivity OAuth callback are
the documented public exceptions; OAuth callback state is independently
validated by the productivity service.

The API bearer token is a shared local API credential, not per-user identity.
Legacy confirmation booleans remain in domain models and service/controller
code but do not authorize the newly disabled Build, GitHub mutation, or Planner
chat paths. The current approval endpoint and task/worker lifecycle retain the
limitations documented in the Phase 12 audit; those are outside this boundary
closure.

Productivity, communication, plugin, memory, settings, and workflow-management
routes remain separate authenticated product APIs, not registered agent
capabilities. Their provider-specific and local-data authorization semantics
require a separate review before they are exposed as autonomous agent actions.

## Verification

`tests/test_execution_boundary.py` asserts that Build execution is unavailable,
GitHub mutations remain unavailable even with `confirmed=true`, read-only Git
status/summary remain available, and the legacy planner does not dispatch
actions. It also covers browser download/upload rejection, the Windows
confirmation flag, exact approval binding/expiry/replay, and revoked-grant
preservation. These tests call handlers directly because the environment's
Starlette `TestClient` portal hangs before request dispatch. API authentication
is covered directly at the middleware boundary by `tests/test_api_authorization.py`.

Verification results for this pass: the execution-boundary suite passed 27
tests; API authorization passed 4; capability routing passed 8; selected Coding
Security, Windows controller, Browser resolver, provider service, and runtime
policy tests passed. TestClient-based Agent Runtime and J2 route integration
tests still cannot run in this environment. The stall is in Python 3.13's
Windows Proactor self-pipe setup: `socket.AF_UNIX` is unavailable, and
`socket.socketpair()` blocks waiting in its TCP fallback `accept()`. The stack
does not reach FastAPI request dispatch, lifespan startup, SQLite, Ollama, or
Playwright. No test dependencies were installed.

An HTTPX `ASGITransport` alternative was investigated with the installed
FastAPI 0.135.2, Starlette 1.3.1, HTTPX 0.28.1, AnyIO 4.14.1, and Python
3.13.3. The API is present and does not itself create a listening socket, but
HTTPX still requires a running asyncio event loop. Both the Proactor and
Selector event loops reach the same blocking `socket.socketpair()` fallback
during loop construction, before an HTTP request can be dispatched. No
`asgi-lifespan`, `pytest-asyncio`, Trio, uvloop, or winloop package is installed.
Therefore an in-process HTTP-level workaround is not available in this
environment without changing the runtime or installing another event-loop
implementation. A Linux-only HTTP test module has since been prepared using
the actual FastAPI app, lifespan context, and HTTPX ASGITransport. It skips on
Windows before the tests run. The temporary workflow
`.github/workflows/phase-13-0-http-verification.yml` runs it alongside the
focused boundary and existing AgentRuntime/J2 route suites on Ubuntu. Neither
the HTTP test module nor workflow has run on Linux yet; the previous direct
handler and middleware results remain the only executed boundary evidence.

## Route inventory revalidation

The current FastAPI application registers 113 routes: 109 under `/api/v1`
(including the API OpenAPI/docs routes) and four framework documentation
routes. All non-public `/api/v1` requests pass through the shared bearer
middleware. `/api/v1/health`, OPTIONS requests, and the productivity OAuth
callback are public exceptions; the OAuth callback validates provider state.

| Route group | Routes | Boundary classification |
|---|---:|---|
| `/agents/*` | 11 | Capability catalog, permission, task, plan, approval, and cancellation API; bearer-protected; task execution uses AgentRuntime |
| `/windows/*` | 1 | Supported operations adapt to AgentRuntime capabilities; sensitive actions require runtime approval |
| `/browser/*` | 5 | Supported operations use the runtime; bookmark is not registered; download/upload fail closed |
| `/coding/*` | 2 | Coding actions use runtime; shell-capable routes also check coding authorization and sensitive commands await approval |
| `/build/*` | 1 | Disabled with 501 |
| `/github/*` | 1 | Status and repository summary are read-only; mutations fail closed with 501 |
| `/chat` | 1 | Deterministic routing; Windows/Browser/Coding supported actions use AgentRuntime; Build and Planner fail closed; GitHub chat mutations fail closed |
| `/automation/*` | 9 | Authenticated manual workflow/plan API; implemented workflow actions are notify/wait; no planner-to-controller dispatch |
| `/communication/*` | 8 | Manual bearer-protected provider API; drafts remain; sending fails closed; provider account operations remain outside AgentRuntime |
| `/productivity/*` | 27 | Manual bearer-protected provider API; email send and Drive delete fail closed; other provider writes remain outside AgentRuntime |
| `/memory/*` | 7 | Manual authenticated local-data API; deterministic memory chat commands can also write/forget directly |
| `/settings/*` | 3 | Manual bearer-protected settings API; outside AgentRuntime |
| `/learning/*` | 6 | Manual bearer-protected observations/preferences/suggestions; approval creates only the limited workflow facility |
| `/documents/*`, `/vision/*` | 9 | Manual bearer-protected file/vision endpoints; outside AgentRuntime |
| `/voice/*` | 7 | Manual bearer-protected voice endpoints; frontend transcript submission can enter `/chat` and reach its supported capability paths |
| `/plugins/*` | 8 | Manual bearer-protected plugin management; load/startup can execute plugin code in a subprocess without an OS sandbox |
| `/ai/*` | 2 | Health/model information endpoints; read-only |
| Health and framework docs | 5 | Health is public; API docs/openapi are within the protected prefix; `/redoc` and OAuth redirect are framework routes outside it |

The shared bearer token is authentication, not independent per-user identity.
Manual Productivity, Communication, Memory, Settings, Learning, Documents,
Voice, Plugin, and Automation APIs are not model-invocable capabilities in the
reviewed chat/runtime path. Their own provider, local-data, and plugin
authorization boundaries remain separate and should not be treated as AgentRuntime
approval. The focused Windows tests do not establish end-to-end HTTP behavior;
that remains blocked pending execution of the temporary Linux workflow.
