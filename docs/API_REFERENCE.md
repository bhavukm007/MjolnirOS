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

---

## GitHub

POST /github/status

POST /github/commit

POST /github/push

POST /github/pull

## Vision & Documents

POST /vision/analyze

Upload an image as `multipart/form-data` field `file` for local OCR, UI recognition, and error detection.

POST /vision/capture

Explicitly capture and analyze the primary desktop.

POST /documents

Upload a PDF, DOCX, XLSX, PPTX, TXT, or Markdown file as `multipart/form-data` field `file`.

GET /documents

GET /documents/{id}

GET /documents/{id}/tables

POST /documents/{id}/summarize

POST /documents/{id}/questions

Input: `{ "question": "..." }`

POST /documents/{id}/translate

Input: `{ "target_language": "Hindi" }`. Translation is performed only through the configured local Ollama instance.

## Automation & Planner

GET /automation/workflows

POST /automation/workflows

PUT /automation/workflows/{id}

DELETE /automation/workflows/{id}

POST /automation/workflows/{id}/executions

Starts a workflow asynchronously. Progress can be queried or cancelled.

GET /automation/executions

GET /automation/executions/{id}

POST /automation/executions/{id}/cancel

POST /automation/plans

Input: `{ "goal": "prepare my coding setup" }`

## Learning Mode

POST /learning/observations

Input: `{ "kind": "application", "value": "VS Code" }`. Learning observations remain local and are used only to infer preferences and suggestions.

GET /learning/overview

GET /learning/preferences

GET /learning/suggestions

POST /learning/suggestions/{id}/approve

Creates a safe custom workflow only after explicit approval.

POST /learning/suggestions/{id}/dismiss

---

## Plugins

GET /plugins

POST /plugins/install

DELETE /plugins/uninstall

POST /plugins/update

## Productivity Plugins

GET /productivity/connections

POST /productivity/oauth/{google|notion}/authorize

GET /productivity/oauth/{google|notion}/callback

DELETE /productivity/connections/{google|notion}

POST /productivity/connections/{google|notion}/sync

Gmail: `GET /productivity/gmail/inbox`, `GET /productivity/gmail/summary`, `GET /productivity/gmail/messages/{id}`, `POST /productivity/gmail/drafts`, `POST /productivity/gmail/messages/{id}/reply-draft`, and `POST /productivity/gmail/drafts/{id}/send`. The send body must be `{ "confirmed": true }`.

Calendar: `GET|POST /productivity/calendar/events`, `PUT|DELETE /productivity/calendar/events/{id}`.

Notion: `GET /productivity/notion/search`, `GET /productivity/notion/pages/{id}`, `POST /productivity/notion/pages`, `POST /productivity/notion/meeting-notes`, and `PATCH /productivity/notion/pages/{id}`.

Drive: `POST|GET /productivity/drive/files`, `GET /productivity/drive/files/{id}/download`, `GET|POST /productivity/drive/folders`, `POST /productivity/drive/files/{id}/move`, and `DELETE /productivity/drive/files/{id}`. Drive deletion requires `{ "confirmed": true }`.

---

## Settings

GET /settings

GET /settings/user

PUT /settings/user

`GET /settings` returns deployment-safe runtime configuration. `GET|PUT /settings/user` reads and persists user preferences.

## Communication Plugins

GET /communication/connections

PUT|DELETE /communication/connections/{provider}

GET /communication/{provider}/conversations

GET /communication/{provider}/search?query=...

POST /communication/{provider}/drafts

POST /communication/drafts/{id}/send requires `{ "confirmed": true }`.

GET /communication/audit/events

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
