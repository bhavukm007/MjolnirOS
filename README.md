<div align="center">
  <img src="assets/branding/mjolnir-app-source.png" alt="MjolnirOS logo" width="160">

# MjolnirOS

Local-first AI desktop assistant for Windows, built with Electron, FastAPI, React, and Ollama.

MjolnirOS brings voice interaction, desktop and browser automation, local memory, document tools, and extensible plugins into one privacy-conscious desktop application.

[![Version](https://img.shields.io/badge/version-1.1.0-2563eb)](https://github.com/bhavukm007/MjolnirOS/releases/tag/v1.1.0)
[![License](https://img.shields.io/badge/license-MIT-16a34a)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows-0078d4)](https://github.com/bhavukm007/MjolnirOS)
[![Python](https://img.shields.io/badge/python-3.12%2B-3776ab)](https://www.python.org/)
[![Node.js](https://img.shields.io/badge/node.js-20%2B-339933)](https://nodejs.org/)
</div>

## Overview

MjolnirOS is designed around local execution and explicit user control. AI requests can use a locally running Ollama model, speech recognition can run with Vosk, and application data is stored on the local machine. Capabilities are separated into focused modules for AI routing, voice, memory, Windows control, browser automation, documents, workflows, and plugins.

Cloud-backed integrations are optional. Actions such as sending communication drafts or deleting provider data require explicit confirmation.

## Screenshots

_Add application screenshots here._

## Why MjolnirOS?

- **Local-first operation:** Core assistant, memory, speech, document, and automation workflows are designed to run on the user's machine.
- **Privacy-conscious storage:** Settings, memory, workflow state, and uploaded documents remain in local runtime storage by default.
- **Modular capabilities:** A deterministic capability router directs requests to specialized modules before using the general AI fallback.
- **Extensible integrations:** A manifest-based plugin system supports isolated plugins with declared permissions and dependency checks.
- **Desktop automation:** Windows and browser controllers expose focused actions through a single desktop interface.
- **User-controlled side effects:** Communication sends and selected destructive provider operations require fresh confirmation.

## Features

### AI runtime

- Local Ollama integration with configurable model and server URL.
- Deterministic routing for browser, Windows, memory, planning, coding, and general-assistant requests.
- Text normalization for common command typos while preserving explicit routing behavior.

### Voice assistant

- Offline speech recognition with Vosk.
- Local text-to-speech through system voices.
- Wake-word sessions, microphone lifecycle management, and speech normalization.

### Windows automation

- Installed-application discovery and launching.
- Focused Windows actions exposed through the assistant API.
- Separation between native application requests and website requests.

### Browser automation

- Playwright-based browser control and page interaction.
- Natural-language browser intent decomposition.
- Browser profile-aware launching, page summaries, and screenshots.

### Vision and documents

- Tesseract-based screenshot OCR, probable button detection, and visible-error detection.
- Local extraction from PDF, DOCX, XLSX, PPTX, TXT, and Markdown files.
- Extractive summaries, table preservation, document questions, and optional local translation through Ollama.

### Automation and learning

- Persisted workflows with dependency-aware execution, progress, and cancellation.
- Goal decomposition through the local planner.
- Local preference learning and user-approved workflow suggestions.

### Productivity and communication

- Productivity integrations for Gmail, Google Calendar, Google Drive, and Notion.
- Communication integrations for Discord, Slack, Telegram, WhatsApp, and Microsoft Teams.
- Local draft storage and explicit confirmation before sends or selected destructive actions.

### Plugin system

- Local plugin catalog with install, update, enable, disable, and uninstall operations.
- Manifest validation, declared permissions, dependency checks, and process-isolated loading.
- Bundled utility and integration plugins.

### Memory

- Persistent local memory for facts, preferences, tasks, and conversational context.
- Explicit remember, query, and forget operations.
- Configurable memory behavior and local vector storage.

### Security

- Windows DPAPI protection for supported OAuth tokens and communication credentials.
- Approval gates for sensitive actions.
- Local audit records that exclude credential and token values.
- Environment-based secrets kept outside source control.

## Technology stack

| Area | Technology | Role |
| --- | --- | --- |
| Desktop | Electron | Native Windows shell, tray integration, and application lifecycle |
| Frontend | React, Vite, Tailwind CSS | Desktop interface and development tooling |
| Backend | FastAPI, Uvicorn | Local API and capability orchestration |
| Language | Python 3.12+, JavaScript | Backend services and desktop/frontend runtime |
| Local AI | Ollama | Local language-model inference |
| Speech | Vosk, pyttsx3 | Offline speech recognition and local text-to-speech |
| Vision | Tesseract, Pillow | OCR and image processing |
| Browser | Playwright | Browser automation |
| Storage | SQLite, Chroma | Runtime state and vector-backed memory |
| Documents | pypdf, python-docx, openpyxl, python-pptx | Local document extraction |
| Packaging | Electron build metadata | Windows icon and NSIS target configuration |
| Containers | Docker, Docker Compose | Optional containerized backend and frontend |

## Project architecture

The Electron shell hosts the React interface and coordinates the local desktop lifecycle. The frontend communicates with a FastAPI service under `/api/v1`. A capability router directs requests to focused services for AI, voice, memory, Windows, browser, automation, vision, plugins, productivity, and communication. Runtime data is stored locally under `database/`.

See the [architecture reference](docs/reference/ARCHITECTURE.md) for component responsibilities and execution flow.

## Project structure

```text
MjolnirOS/
├── assets/             # Application icons and production branding
├── backend/            # FastAPI application and capability services
├── config/             # Checked-in default configuration
├── database/           # Local runtime storage root
├── desktop/            # Electron main process and preload bridge
├── docs/               # Guides, references, releases, and history
├── frontend/           # React and Tailwind CSS interface
├── plugins/            # Bundled plugins and local catalog
├── scripts/            # Development and branding utilities
└── tests/              # Backend and integration tests
```

## Getting started

### Prerequisites

| Requirement | Version or purpose |
| --- | --- |
| Windows | Required for desktop, DPAPI, tray, and Windows automation features |
| Python | 3.12 or newer |
| Node.js | 20 or newer |
| npm | 10 or newer |
| Ollama | Local language-model runtime |
| Tesseract OCR | Required for screenshot OCR and vision analysis |
| Vosk model | Optional unless offline voice recognition is used |

### Install external tools

Install [Ollama](https://ollama.com/) and pull the default model:

```powershell
ollama pull qwen2.5:3b
```

Install Tesseract OCR on Windows:

```powershell
winget install --id UB-Mannheim.TesseractOCR -e
```

For offline speech recognition, download a compatible Vosk model and place it at:

```text
assets/models/vosk-model-small-en-us-0.15/
```

The model directory is intentionally excluded from Git.

## Installation

```powershell
git clone https://github.com/bhavukm007/MjolnirOS.git
cd MjolnirOS

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

npm install
npm install --prefix frontend

Copy-Item .env.example .env
```

Review `.env` before starting the application, especially the Ollama model, Tesseract path, OAuth credentials, and local storage settings.

## Running the project

### Integrated development mode

Start the backend, frontend, and Electron shell together:

```powershell
npm run dev
```

### Run components separately

Use separate terminals when starting each component individually:

```powershell
# Backend: http://127.0.0.1:8000/api/v1
npm run backend:dev

# Frontend: http://127.0.0.1:5173
npm run frontend:dev

# Electron shell
npm run desktop:dev
```

### Docker

The backend and frontend can also be started with Docker Compose:

```powershell
docker compose up --build
```

Docker does not replace Windows-specific desktop functionality provided by Electron.

## Configuration

MjolnirOS loads checked-in defaults from `config/app.json`. Environment variables prefixed with `MJOLNIROS_` can override local settings; copy `.env.example` to `.env` for development values and secrets.

Common settings include:

| Setting | Purpose |
| --- | --- |
| `MJOLNIROS_DEFAULT_MODEL` | Ollama model used by the assistant |
| `MJOLNIROS_OLLAMA_URL` | Local Ollama server URL |
| `MJOLNIROS_TESSERACT_COMMAND` | Full path to `tesseract.exe` when it is not on `PATH` |
| `MJOLNIROS_VISION_UPLOAD_DIRECTORY` | Local document upload directory |
| `MJOLNIROS_AUTOMATION_STORAGE_DIRECTORY` | Persisted workflow directory |
| `MJOLNIROS_LEARNING_STORAGE_DIRECTORY` | Local learning-state directory |

Voice recognition uses the configured Vosk model path, which defaults to `assets/models/vosk-model-small-en-us-0.15`. Productivity integrations require provider credentials from `.env`; they are optional until an integration is connected.

## Documentation

| Document | Description |
| --- | --- |
| [Installation guide](docs/guides/INSTALLATION_GUIDE.md) | Detailed setup and installation guidance |
| [User guide](docs/guides/USER_GUIDE.md) | Using the desktop assistant and its capabilities |
| [Architecture](docs/reference/ARCHITECTURE.md) | Components, boundaries, and execution model |
| [API reference](docs/reference/API_REFERENCE.md) | Local API endpoints and conventions |
| [Plugin SDK](docs/reference/PLUGIN_SDK.md) | Plugin structure, permissions, and lifecycle |
| [Security](docs/reference/SECURITY.md) | Security principles and sensitive operations |
| [Testing](docs/guides/TESTING.md) | Test strategy and verification commands |
| [Roadmap](docs/releases/ROADMAP.md) | Current maintenance line and future planning |
| [Release notes](docs/releases/RELEASE_NOTES.md) | In-repository release summary |
| [Contributing](docs/guides/CONTRIBUTING.md) | Contribution workflow and project conventions |

## Current status

MjolnirOS v1.1.0 provides the local desktop shell, deterministic capability routing, Ollama integration, voice and text normalization, Windows and browser routing, local memory, document processing, automation, plugins, productivity integrations, communication drafts, and persisted settings.

Development is ongoing. Live weather, news, sports, and currency providers are not yet implemented, and the repository does not currently publish a packaged Windows installer. The application should be run from source.

## Roadmap

Current areas of work include live-information providers, production installer packaging, user-selectable browser profiles, broader automation adapters, and continued reliability and performance improvements.

See the [detailed roadmap](docs/releases/ROADMAP.md) for maintained planning information.

## Contributing

Contributions should follow the repository's coding, testing, security, and review conventions. Start with the [contribution guide](docs/guides/CONTRIBUTING.md).

## License

MjolnirOS is available under the [MIT License](LICENSE).
