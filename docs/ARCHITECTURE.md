# MjolnirOS Architecture

Version: 1.0

This document defines the architecture of MjolnirOS.

All future implementations must follow this architecture.

---

# High Level Architecture

MjolnirOS follows a modular multi-agent architecture.

Every major feature is isolated into its own module.

No module should directly depend on another module unless required.

Communication should happen through internal APIs and events.

```
                    User

                     │

              Voice / UI

                     │

          Conversation Agent

                     │

             Planner Agent

                     │

──────────────────────────────────────────

 Memory      Browser      Coding

 Windows     GitHub       Vision

 Documents   Automation   Plugins

                     │

         Permission Manager

                     │

          Execution Engine

                     │

               Windows OS

```

---

# Core Components

The system consists of:

- Desktop Application
- Backend API
- AI Engine
- Agents
- Memory
- Plugin Manager
- Windows Controller
- Browser Controller
- Coding Controller
- Vision System

---

# Folder Structure

```
MjolnirOS/

backend/
frontend/
desktop/
agents/
browser/
coding/
github/
memory/
plugins/
speech/
vision/
windows/
automation/
permissions/
database/
config/
system/
api/
tests/
docs/
scripts/
assets/
logs/
```

---

# Desktop Layer

Responsible for:

- Electron Window
- Tray Icon
- Startup
- Settings
- Dashboard
- Notifications

Technology

Electron

React

TailwindCSS

---

# Backend Layer

Technology

FastAPI

Responsibilities

- API
- AI orchestration
- Plugin loading
- Memory
- Automation
- System services

---

# AI Layer

The AI Layer is powered by

Ollama

Default model

qwen2.5:3b

Responsibilities

- Natural conversation
- Reasoning
- Planning
- Task decomposition

Future models should be selectable.

---

# Conversation Agent

Responsible for:

- Chat
- Context
- Intent detection
- Conversation history

The Conversation Agent never directly controls Windows.

It only creates plans.

---

# Planner Agent

Responsibilities

- Break tasks into steps
- Select required agents
- Execute safely

Example

User:

"Organize my Downloads and push my Portfolio."

Planner

↓

Windows Agent

↓

GitHub Agent

---

# Memory Agent

Responsibilities

Store

- conversations
- notes
- todos
- preferences
- projects
- workflows

Technology

SQLite

ChromaDB

---

# Windows Agent

Controls

Applications

Explorer

Clipboard

CPU

RAM

GPU

Battery

Power

Processes

Notifications

Task Manager

---

# Browser Agent

Technology

Playwright

Responsibilities

- Search
- Login
- Read webpages
- Fill forms
- Upload
- Download

Supported browsers

Chrome

Edge

Firefox

---

# Coding Agent

Responsibilities

- VS Code
- Git
- Docker
- Terminal
- Code Generation
- Debugging
- Refactoring

---

# GitHub Agent

Responsibilities

Clone

Commit

Push

Pull

Branches

Repositories

Issues

Pull Requests

Never perform destructive Git commands without permission.

---

# Document Agent

Supports

PDF

DOCX

XLSX

PPTX

TXT

Markdown

Responsibilities

Read

Summarize

Extract

Translate

---

# Vision Agent

Responsibilities

OCR

Screenshot analysis

Desktop understanding

UI detection

Future

Camera understanding

## Phase 10 implementation

The Vision & Document Agent is implemented in `backend/app/vision`. `DocumentService` accepts supported uploads, stores them in the local application data directory, extracts text and tables through format-specific adapters, and supplies offline extractive summaries and question answers. `VisionService` uses locally installed Tesseract OCR for screenshot text, probable button labels, and visible error detection. The API route remains the integration boundary; neither service depends on the desktop UI.

## Phase 11 implementation

The Automation Engine is implemented in `backend/app/automation`. `AutomationService` persists workflow definitions and runs safe, dependency-aware steps while publishing durable execution status. `PlannerService` converts natural-language goals into transparent task plans and selects a matching routine when possible. The API starts execution asynchronously so the frontend can display progress or request cancellation; future agent action adapters can extend the engine without changing workflow storage or planner contracts.

## Phase 12 implementation

Learning Mode is implemented in `backend/app/learning`. `LearningService` stores typed, non-sensitive local observations, derives durable preference inferences, and detects recurring routines. Suggestions are persisted in a pending state and may create an Automation workflow only through the explicit approval endpoint. This keeps learning observational and privacy-first while allowing later agents to record activity through the same stable API.

## Phase 13 implementation

The Plugin System is implemented in `backend/app/plugins`. `PluginService` discovers versioned plugin folders, validates manifests, declared permissions, and dependency versions, and invokes entry points in a separate isolated Python interpreter so plugin code never enters the FastAPI process. The API and dashboard provide local marketplace discovery, categories, search, dynamic loading, installation, updates, and safe dependency-aware removal. Plugins remain extension packages with the stable `manifest.json`, `permissions.json`, `plugin.py`, and `README.md` contract.

---

# Plugin Manager

Plugins are loaded dynamically.

Plugin folder

```
plugins/

spotify/

gmail/

calendar/

docker/

aws/
```

Each plugin contains

```
manifest.json

plugin.py

permissions.json

README.md
```

Plugin Manager loads plugins automatically.

---

# Permission Manager

Every dangerous operation must pass through this module.

Examples

Delete Files

Install Software

Registry

Admin

Git Reset

Git Force Push

Email Send

Permission dialog should explain:

- What will happen
- Files affected
- Can it be undone

---

# Execution Engine

Receives approved tasks.

Executes

Returns results.

Reports failures.

Logs everything.

---

# Event System

MjolnirOS uses internal events.

Example

```
Wake Word

↓

Conversation

↓

Planner

↓

Windows Agent

↓

Execution

↓

Response
```

---

# Logging

Every module writes structured logs.

Levels

INFO

WARNING

ERROR

CRITICAL

Store logs in

```
logs/
```

---

# Configuration

Centralized.

Stored in

```
config/
```

No hardcoded values.

---

# Database

SQLite

Application data

ChromaDB

Semantic memory

---

# Security

Secrets stored securely.

Never hardcode

Passwords

Tokens

Keys

API secrets

---

# Startup Sequence

Windows Login

↓

Auto Start

↓

Load Config

↓

Load Database

↓

Load Plugins

↓

Connect Ollama

↓

Start Wake Word

↓

Idle

---

# Shutdown Sequence

Save memory

Flush logs

Stop agents

Disconnect Ollama

Exit safely

---

# Future Expansion

Architecture should support

- Multiple AI models
- Remote devices
- Android companion app
- Linux
- macOS
- Home Automation
- Smart Devices
- Multi-user support

---

# Architecture Rules

Every module should

- Be independent
- Have a single responsibility
- Be testable
- Be replaceable
- Have clear interfaces

No circular dependencies.

Follow Clean Architecture.

This document is the official architecture reference for MjolnirOS.

## Phase 14 implementation

Productivity integrations are implemented behind `backend/app/productivity` and the `/productivity` API boundary. Provider-facing OAuth and HTTP work is centralized there so process-isolated plugin packages never receive or persist credentials. The dashboard only receives safe connection metadata. Windows DPAPI protects local OAuth token storage, while confirmation-gated Gmail sending and Drive deletion preserve the Permission Manager boundary.
