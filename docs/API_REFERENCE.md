# API Reference

Version: 1.0

This document defines the internal API structure of MjolnirOS.

---

# API Principles

- RESTful APIs
- JSON Responses
- Proper HTTP Status Codes
- Authentication where required
- Modular endpoints

---

# Base URL

http://localhost:8000/api/v1

---

# Core Endpoints

## Health

GET /health

Returns application status.

---

## Chat

POST /chat

Input:

- message

Output:

- response

- conversation_id

Phase 03 streams newline-delimited JSON events. Token events contain `type: "token"` and `content`; terminal events contain `type: "done"` or `type: "error"`.

## Local AI

GET /ai/health

Returns local Ollama availability and whether the configured default model is installed.

GET /ai/models

Returns models installed in the local Ollama runtime.

---

## Memory

GET /memory

POST /memory

DELETE /memory/{id}

---

## Windows

POST /windows/open

POST /windows/close

POST /windows/search

GET /windows/system

---

## Browser

POST /browser/open

POST /browser/search

POST /browser/download

POST /browser/upload

POST /browser/actions

Browser actions provide structured success or failure data. Credentials are never accepted by the API; login requests open the page and require the user to enter credentials, MFA, and CAPTCHA responses directly in the browser. Form submission and executable downloads require `confirmed: true`.

---

## GitHub

POST /github/status

POST /github/commit

POST /github/push

POST /github/pull

POST /github/actions

GitHub actions return structured results. Force pushes, merges, branch deletion, public repository creation, and pulls over local changes require `confirmed: true`. Tokens are only read from the current process environment and are never returned.

## Coding

POST /coding/actions

Coding actions open VS Code workspaces, folders, and files; reveal files; open the integrated terminal; execute commands with captured stdout, stderr, and exit code; and manage remembered workspaces. Commands containing destructive operations require `confirmed: true`.

POST /coding/ai/actions

Local Ollama Coding Agent actions generate code, explain code and SQL, debug errors, explain errors, analyse compiler output, and suggest fixes for Python, C++, Java, JavaScript, and SQL. Responses are structured and coding conversations stay in local memory.

POST /build/actions

Build actions provide local Docker operations, dependency resolution, project generation, compile/run adapters, and project registration. Global package installs and privileged Docker containers require `confirmed: true`.

---

## Plugins

GET /plugins

POST /plugins/install

DELETE /plugins/uninstall

POST /plugins/update

---

## Settings

GET /settings

PUT /settings

---

## Logs

GET /logs

---

## Agents

GET /agents

POST /agents/start

POST /agents/stop

---

All endpoints must return

{
    "success": true,
    "message": "",
    "data": {}
}
