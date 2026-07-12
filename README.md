# MjolnirOS

MjolnirOS is a local-first Windows desktop operating assistant built with FastAPI, Electron, React, and Tailwind CSS. It includes the Phase 10 Vision & Document Agent, with private document processing and screenshot understanding.

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

## Automation & Planner

The Automation Engine stores workflows locally in `database/automation/`. Built-in workflows are safe orchestration templates for morning, coding, study, placement preparation, interview, presentation, gaming, and shutdown routines. Custom workflows support `notify` and `wait` steps today; later agent integrations can add action adapters without changing stored workflow definitions. The planner maps common goals to an appropriate routine or returns a transparent generic plan.

## Vision & Document setup

OCR requires [Tesseract OCR](https://github.com/tesseract-ocr/tesseract). On Windows, install it with `winget install --id UB-Mannheim.TesseractOCR -e`, then restart the terminal so the installer can add it to `PATH`. MjolnirOS checks an explicitly configured `MJOLNIROS_TESSERACT_COMMAND` first, then `PATH`, then standard Windows installation roots. If the executable is installed elsewhere, set `MJOLNIROS_TESSERACT_COMMAND` to its full path. Uploads are stored locally in `database/documents/`, are limited to 20 MB by default, and can be configured through `config/app.json` or environment variables.

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
