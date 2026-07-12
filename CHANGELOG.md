# Changelog

All notable changes to MjolnirOS will be documented in this file.

## [0.6.0] - 2026-07-12

### Added

- Added the local Windows Control Agent with application, Explorer, file, system, clipboard, screenshot, Task Manager, network, Bluetooth, and power utilities.
- Added structured Windows action responses and mandatory confirmation gates for file deletion and Recycle Bin emptying.

## [0.5.0] - 2026-07-12

### Added

- Added local SQLite memory storage with automatic schema migrations.
- Added persistent ChromaDB semantic indexing and memory APIs.
- Added automatic conversation persistence and typed memories for preferences, notes, todos, bookmarks, projects, workflows, GitHub repositories, coding preferences, and folder locations.

## [0.4.0] - 2026-07-12

### Added

- Added offline Vosk speech recognition with continuous low-overhead microphone streaming.
- Added tolerant Mjolnir wake-word detection, including common phonetic pronunciations.
- Added offline operating-system text-to-speech and immediate speech interruption for barge-in.
- Added voice API endpoints, voice runtime health checks, centralized voice configuration, and regression tests.

## [0.3.0] - 2026-07-12

### Added

- Added a local Ollama client with availability monitoring and installed-model discovery.
- Added streamed NDJSON chat responses through `POST /api/v1/chat`.
- Added a local chat workspace with model selection and graceful offline handling.
- Added centralized Ollama connection configuration and AI runtime tests.

## [0.2.0] - 2026-07-11

### Added

- Added the Electron desktop runtime with a Windows system tray and restore controls.
- Added minimize-to-tray behavior, tray actions for open, settings, restart, and quit, and structured desktop logging.
- Added a dedicated settings window with a persisted, opt-in Windows startup preference that defaults to disabled.
- Added live CPU, RAM, current-model, and running-agent dashboard metrics.
- Added `npm run dev` to launch FastAPI, Vite, and Electron together.
- Added desktop runtime and settings persistence tests.

## [0.1.0] - 2026-07-11

### Added

- Initialized Phase 01 project foundation.
- Added FastAPI backend with structured logging and centralized configuration.
- Added React and Tailwind CSS dashboard connected to backend health data.
- Added Electron desktop shell with smoke launch validation.
- Added Docker support, tests, README, license, and environment example.
