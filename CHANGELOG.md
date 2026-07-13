# Changelog

All notable changes to MjolnirOS will be documented in this file.

## [1.0.1] - 2026-07-13

### Fixed

- Restored environment and `.env` precedence over `config/app.json` and made FastAPI startup use its injected application settings.
- Moved blocking provider operations out of async route handlers, removed the accidental frontend root-package dependency, and made the frontend Docker image deterministic and production-static.
- Synchronized Electron login/tray settings immediately after a user settings update and restored the tray restart/settings actions.
- Hardened plugin metadata validation by rejecting duplicate and incomplete permission declarations.

## [1.0.0] - 2026-07-13

### Added

- Added versioned isolated Discord, Slack, WhatsApp, Telegram, and Microsoft Teams communication plugins.
- Added DPAPI-backed credentials, supported conversation reads/search, persisted drafts, explicit send confirmation, and audit logging.
- Added persistable startup, tray, appearance, Ollama, memory, and notification settings plus enabled-plugin startup restoration.

## [0.14.0] - 2026-07-13

### Added

- Added process-isolated Gmail, Google Calendar, Notion, and Google Drive productivity plugins with manifests, semantic versions, and reviewed permissions.
- Added OAuth authorization, secure Windows DPAPI token storage, state validation, provider connection status, and Google token refresh.
- Added Gmail inbox/search/summary/draft/reply APIs, with explicit confirmation required for every send.
- Added Calendar event search, timezone-aware creation, updating, deletion, and conflict detection; Notion page/search APIs; and Drive file/folder operations with confirmation-gated deletion.
- Added the Productivity management dashboard for connection state, account display, manual sync, errors, and health indicators.

## [0.13.0] - 2026-07-12

### Added

- Added the local Plugin SDK, manifest and permissions validation, semantic-version dependency checks, and process-isolated dynamic loading.
- Added plugin install, uninstall, update, marketplace search, category, and management APIs with dashboard controls.
- Added packaged Spotify, Weather, Calculator, Clock, GitHub, and Docker plugins plus API coverage for plugin lifecycle and permission validation.
- Added the navigable React Plugin Manager with installed and marketplace views, search, category filtering, and lifecycle controls.
- Added persistent enabled/disabled plugin state and frontend integration coverage for plugin activation.
- Hardened plugin discovery against malformed metadata, missing files, dependency cycles, and atomic state persistence.

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
