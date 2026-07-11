# MjolnirOS

MjolnirOS is a local-first Windows desktop operating assistant built with FastAPI, Electron, React, and Tailwind CSS. Phase 01 establishes the production foundation only: project structure, centralized configuration, structured logging, backend API, frontend dashboard, Electron shell, Docker support, and tests.

## Phase 01 Scope

- FastAPI backend with `/api/v1/health` and `/api/v1/settings`.
- React dashboard that reads backend health and configuration state.
- Electron desktop shell with smoke validation.
- Centralized JSON and environment-based configuration.
- Structured JSON logging to console and `logs/mjolniros.log`.
- Docker Compose support for backend and frontend.

Future capabilities such as Ollama chat, voice, memory, Windows automation, browser automation, plugins, and tray behavior are intentionally reserved for later documented phases.

## Requirements

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
