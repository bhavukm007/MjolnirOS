# MjolnirOS

MjolnirOS is a local-first Windows desktop operating assistant built with FastAPI, Electron, React, and Tailwind CSS. Phases 01 and 02 establish the production foundation and desktop runtime: project structure, centralized configuration, structured logging, backend API, a live dashboard, Electron tray behavior, settings, Docker support, and tests.

## Current Scope

- FastAPI backend with `/api/v1/health` and `/api/v1/settings`.
- React dashboard that reads backend health, configuration, CPU, RAM, current model, and active agent count.
- Electron desktop runtime with a system tray, minimize-to-tray lifecycle, restore controls, and smoke validation.
- Dedicated settings window with a persisted, opt-in Windows startup preference. Startup is off by default.
- Centralized JSON and environment-based configuration.
- Structured JSON logging to console and `logs/mjolniros.log`.
- Docker Compose support for backend and frontend.

Future capabilities such as Ollama chat, voice, memory, Windows automation, browser automation, and plugins are intentionally reserved for later documented phases.

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

Start the backend, frontend, and Electron desktop application together:

```powershell
npm run dev
```

The development command keeps the desktop runtime open in the system tray when its main window is minimized or closed. Use the tray menu to open the dashboard, open settings, restart, or quit.

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

In Settings, **Launch MjolnirOS when Windows starts** remains disabled until you turn it on. When enabled, MjolnirOS registers the current application with Windows login; disabling the setting removes that registration. The preference is stored in Electron's local application data.

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
