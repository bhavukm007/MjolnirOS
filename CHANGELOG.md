# Changelog

All notable changes to MjolnirOS will be documented in this file.

## [0.13.0] - 2026-07-12

### Added

- Added the local Plugin SDK, manifest and permissions validation, semantic-version dependency checks, and process-isolated dynamic loading.
- Added plugin install, uninstall, update, marketplace search, category, and management APIs with dashboard controls.
- Added packaged Spotify, Weather, Calculator, Clock, GitHub, and Docker plugins plus API coverage for plugin lifecycle and permission validation.
- Added the navigable React Plugin Manager with installed and marketplace views, search, category filtering, and lifecycle controls.
- Added persistent enabled/disabled plugin state and frontend integration coverage for plugin activation.

## [0.12.0] - 2026-07-12

### Added

- Added the local Learning Mode observation store, preference inference, and repeat-pattern detection.
- Added approval-gated workflow suggestions that integrate with the Automation Engine only after user confirmation.
- Added Learning Mode APIs, dashboard controls, and persistence tests.

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
