# MjolnirOS

MjolnirOS is a local-first Windows desktop operating assistant built with FastAPI, Electron, React, and Tailwind CSS. Phases 01 through 04 establish the production foundation, desktop runtime, local AI runtime, and offline voice interaction.

## Current Scope

- FastAPI backend with `/api/v1/health` and `/api/v1/settings`.
- React dashboard that reads backend health, configuration, CPU, RAM, current model, and active agent count.
- Electron desktop runtime with a system tray, minimize-to-tray lifecycle, restore controls, and smoke validation.
- Dedicated settings window with a persisted, opt-in Windows startup preference. Startup is off by default.
- Local Ollama health monitoring, installed-model selection, and streamed chat responses.
- Offline continuous microphone listening with Vosk speech recognition, tolerant “Mjolnir” wake-word matching, local text-to-speech, and natural speech interruption.
- Centralized JSON and environment-based configuration.
- Structured JSON logging to console and `logs/mjolniros.log`.
- Docker Compose support for backend and frontend.

MjolnirOS now persists conversations and typed local memories using SQLite, with ChromaDB semantic retrieval. Windows automation, browser automation, and plugins are reserved for later documented phases.

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

## Local AI

MjolnirOS uses the local Ollama API at `http://127.0.0.1:11434/api` by default. Install and run Ollama, then make sure the configured default model is available:

```powershell
ollama pull qwen2.5:3b
```

The dashboard reports when Ollama is unavailable and does not send data to any cloud provider. The Ollama base URL and timeout can be configured with `MJOLNIROS_OLLAMA_BASE_URL` and `MJOLNIROS_OLLAMA_TIMEOUT_SECONDS`.

## Voice

Voice recognition stays local using Vosk and the operating system's offline voices. Download the small English Vosk model from the [official Vosk models page](https://alphacephei.com/vosk/models), extract it to `assets/models/vosk-model-small-en-us-0.15`, then start MjolnirOS and select **Start voice**. Say “Mjolnir” (for example, “Me-oh-neer”) before a request. Speaking while MjolnirOS is replying interrupts local speech naturally. Configure the model path, sample rate, wake word, and voice output through the `MJOLNIROS_VOICE_*` variables in `.env.example`.

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
