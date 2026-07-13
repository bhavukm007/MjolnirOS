# MjolnirOS

MjolnirOS is a local-first Windows desktop operating assistant built with FastAPI, Electron, React, and Tailwind CSS. Version 1.0 includes private vision/document processing, automation, learning, plugins, productivity integrations, communication drafts, and persisted desktop settings.

## Current capabilities

- FastAPI backend with `/api/v1/health` and `/api/v1/settings`.
- React dashboard that reads backend health and configuration state.
- Electron desktop shell with smoke validation.
- Centralized JSON and environment-based configuration.
- Structured JSON logging to console and `logs/mjolniros.log`.
- Docker Compose support for backend and frontend.
- Drag-and-drop local processing for PDF, DOCX, XLSX, PPTX, TXT, and Markdown documents.
- Extractive document summaries, table extraction, and offline document questions.
- Screenshot OCR, probable button recognition, and visible error detection using Tesseract.
- Optional document translation through a locally running Ollama model; no document data is sent to a cloud service.
- Automation Engine & Planner with built-in routines, saved custom workflows, visible dependency-aware progress, cancellation, and local goal decomposition.
- Learning Mode with local habit observations, inferred preferences, and user-approved automation recommendations.
- Plugin Manager with a local marketplace, manifest validation, dependency checks, permission declarations, and restart-free isolated loading.
- Productivity plugins for Gmail, Google Calendar, Notion, and Google Drive with OAuth connections, provider health, and manual sync controls.
- Communication plugins for Discord, Slack, WhatsApp Cloud API, Telegram, and Microsoft Teams. They save drafts locally and require a fresh confirmation for every message send.
- Persisted desktop settings for startup, tray behavior, appearance, Ollama, memory, notifications, and local security controls.

## Learning Mode

Learning Mode stores local, non-sensitive activity observations in `database/learning/`. It can infer preferred applications, IDEs, browsers, folders, repositories, coding styles, and frequently used commands. After a pattern repeats, MjolnirOS proposes a safe workflow; it never creates or runs automation until the user explicitly approves the suggestion.

## Automation & Planner

The Automation Engine stores workflows locally in `database/automation/`. Built-in workflows are safe orchestration templates for morning, coding, study, placement preparation, interview, presentation, gaming, and shutdown routines. Custom workflows support `notify` and `wait` steps today; later agent integrations can add action adapters without changing stored workflow definitions. The planner maps common goals to an appropriate routine or returns a transparent generic plan.

## Vision & Document setup

OCR requires [Tesseract OCR](https://github.com/tesseract-ocr/tesseract). On Windows, install it with `winget install --id UB-Mannheim.TesseractOCR -e`, then restart the terminal so the installer can add it to `PATH`. MjolnirOS checks an explicitly configured `MJOLNIROS_TESSERACT_COMMAND` first, then `PATH`, then standard Windows installation roots. If the executable is installed elsewhere, set `MJOLNIROS_TESSERACT_COMMAND` to its full path. Uploads are stored locally in `database/documents/`, are limited to 20 MB by default, and can be configured through `config/app.json` or environment variables.

Cloud synchronization, mobile access, voice calling, and enterprise deployment are intentionally outside the v1.0 scope.

## Plugin System

Phase 13 provides a local-first plugin SDK. On first use, the Plugin Manager materializes the Spotify, Weather, Calculator, Clock, GitHub, and Docker plugins in `plugins/`. Each plugin has `manifest.json`, `permissions.json`, `plugin.py`, and `README.md`. The dashboard marketplace supports category browsing, search, loading, installation, updates, and uninstallation without a backend restart.

Use the **Plugin Manager** navigation item to browse installed extensions or the local marketplace. Enabled state is persisted locally in `database/plugins/state.json`, so an enabled plugin remains enabled after restart; disabling keeps its files available for later activation.

Plugins declare reviewed capabilities including `automation`, `browser`, `memory`, `network`, `system`, and provider-specific integration permissions. The manager validates manifests, permission combinations, semantic-version dependencies, and dependency cycles before activation, then invokes the entry point in a separate isolated Python interpreter process. This prevents plugin code from being imported into the API process; OS-level access should still be granted only through the existing approval-gated agents.

## Communication and security

Communication credentials are protected with the current Windows user's DPAPI key in `database/communication/`; they are never returned by the API or loaded by isolated plugin processes. Drafts remain unsent until the send request includes `{"confirmed": true}`. Voice calling is intentionally reserved for a future plugin interface.

## Requirements

## Productivity plugin setup

Gmail, Google Calendar, Google Drive, and Notion are independent Phase 14 plugins. Add OAuth client credentials to a local `.env` file using the names in `.env.example`; do not commit those values. Register the loopback redirect URIs with Google and Notion, start MjolnirOS, then open **Productivity** and select **Connect**. OAuth tokens are protected with the current Windows user's DPAPI key in `database/productivity/` and are never returned through the API or shown in the UI.

Google uses Gmail modify, Calendar, and Drive scopes only. Sending a Gmail draft and deleting a Drive file each require `{"confirmed": true}` on that operation; drafts are never sent automatically. Calendar creation checks the requested time window for conflicts before creating an event.

- Python 3.12+
- Node.js 20+
- npm 10+

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
npm install
```

## Run Locally

Start the backend:

```powershell
npm run backend:dev
```

Start the frontend:

```powershell
npm run frontend:dev
```

Launch Electron:

```powershell
npm run desktop:dev
```

The API is served at `http://127.0.0.1:8000/api/v1`.

## Verification

```powershell
npm test
npm run build
npm run launch:smoke
```

## Docker

```powershell
docker compose up --build
```
