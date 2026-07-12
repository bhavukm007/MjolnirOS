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
