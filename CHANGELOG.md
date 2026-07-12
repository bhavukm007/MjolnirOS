# Changelog

All notable changes to MjolnirOS will be documented in this file.

## [0.11.0] - 2026-07-12

### Added

- Added the Automation Engine with persisted built-in and custom workflows.
- Added dependency-aware execution, progress reporting, cancellation, and safe local `notify` and `wait` actions.
- Added deterministic goal decomposition through the Planner API and dashboard controls for recording, editing, running, and deleting custom workflows.

## [0.10.0] - 2026-07-12

### Added

- Added the local Vision & Document Agent with drag-and-drop processing for PDF, DOCX, XLSX, PPTX, TXT, and Markdown.
- Added document extraction, table preservation, offline summaries, extractive question answering, and local Ollama translation.
- Added screenshot OCR, visible error detection, and probable button recognition.
- Added Phase 10 API and frontend integration tests.

## [0.1.0] - 2026-07-11

### Added

- Initialized Phase 01 project foundation.
- Added FastAPI backend with structured logging and centralized configuration.
- Added React and Tailwind CSS dashboard connected to backend health data.
- Added Electron desktop shell with smoke launch validation.
- Added Docker support, tests, README, license, and environment example.
