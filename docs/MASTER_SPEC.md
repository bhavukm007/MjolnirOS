# MjolnirOS - Master Specification

Version: 1.0

Project Status: In Development

Repository: MjolnirOS

Target Platform: Windows 11

Primary Language: Python 3.12+

Desktop Framework: Electron + React

Backend: FastAPI

Local AI: Ollama

Default Model: qwen2.5:3b

---

# Vision

MjolnirOS is a production-quality personal AI Operating System that runs locally on Windows.

Its purpose is to become the user's primary desktop assistant capable of understanding natural language, remembering information, automating tasks, controlling Windows, coding, browsing, managing GitHub, and continuously learning the user's workflow.

MjolnirOS is NOT a chatbot.

MjolnirOS is a desktop operating assistant.

Everything possible should work locally without paid APIs.

---

# Core Principles

- Local First
- Privacy First
- Modular
- Plugin Based
- Production Quality
- Extensible
- Secure
- Maintainable
- Fast
- Always Runnable

---

# Primary Goals

MjolnirOS should:

- Run continuously in the background.
- Automatically start when Windows starts.
- Wake when user says "Mjolnir".
- Understand spoken English.
- Respond naturally.
- Execute commands safely.
- Remember information permanently.
- Learn workflows.
- Be extensible using plugins.

---

# AI Model

The default model is:

Ollama

qwen2.5:3b

No paid API should be required.

Future support:

- DeepSeek
- Llama
- Gemma
- Phi
- Mistral

The model should be changeable from Settings.

---

# Voice

Wake Word:

Mjolnir

Pronunciation:

Me-oh-neer

Requirements:

- Always listening in background
- Low CPU usage
- Fast wake time
- Natural conversation
- Streaming responses

---

# Memory

MjolnirOS should permanently remember:

- User preferences
- Projects
- Folder locations
- Conversations
- Notes
- Todos
- GitHub repositories
- Frequently used commands
- Workflows
- Coding preferences

Memory must survive restarts.

Use semantic search.

---

# Windows Integration

MjolnirOS should control:

- Applications
- Files
- Explorer
- Clipboard
- Notifications
- Task Manager
- CPU
- RAM
- GPU
- Battery
- Wi-Fi
- Bluetooth
- Power Options

---

# Browser

Support:

- Chrome
- Edge
- Firefox

Capabilities:

- Search Google
- Read webpages
- Summarize
- Login
- Fill forms
- Upload files
- Download files
- Manage tabs

Playwright should be used.

---

# Coding Agent

Deep VS Code integration.

Capabilities:

- Generate code
- Modify code
- Refactor
- Explain
- Debug
- Run code
- Docker
- Terminal
- Dependency management

Supported languages:

- Python
- C++
- Java
- JavaScript
- SQL

---

# GitHub Agent

Support:

- Clone
- Pull
- Push
- Commit
- Branches
- Merge
- Repository creation
- Pull Requests
- Issues

Automatically generate commit messages.

Never perform force push without permission.

---

# Document Agent

Support:

- PDF
- Word
- Excel
- PowerPoint
- Markdown
- Text

Capabilities:

- Read
- Summarize
- Translate
- Extract data

---

# Vision

Capabilities:

- OCR
- Screenshot analysis
- Desktop understanding
- Error explanation
- UI recognition

Future:

- Webcam support

---

# Automation

MjolnirOS should automate:

Morning Routine

Coding Mode

Study Mode

Interview Mode

Presentation Mode

Gaming Mode

Users should also be able to create custom workflows.

---

# Learning Mode

Observe repeated user behaviour.

Suggest automations.

Allow editing workflows.

Replay saved workflows.

---

# Plugin Marketplace

MjolnirOS must support dynamic plugins.

Each plugin should be isolated.

Plugin examples:

- Spotify
- Gmail
- Calendar
- Discord
- Slack
- Docker
- AWS
- Weather
- WhatsApp
- Notion
- LeetCode

Users should be able to install and uninstall plugins without modifying the core application.

---

# Permissions

Sensitive actions always require confirmation.

Examples:

- Delete files
- Send emails
- Install software
- Registry edits
- Administrator commands
- Git reset
- Git force push

Never bypass confirmations.

---

# Startup Behaviour

After Windows login:

- Launch automatically
- Hide in system tray
- Load settings
- Load plugins
- Load memory
- Start Ollama connection
- Start wake-word detection

Closing the window should minimize to tray.

Provide:

- Quit
- Restart
- Settings

inside tray menu.

---

# User Interface

Theme:

Dark

Design:

Modern

Glassmorphism

Smooth animations

Dashboard should display:

- CPU
- RAM
- GPU
- Running agents
- Current model
- Memory usage
- Tasks
- Logs
- Plugin status

---

# Engineering Standards

Follow:

- Clean Architecture
- SOLID Principles
- Type Hints
- Modular Design
- Unit Tests
- Integration Tests
- Structured Logging

Never leave TODOs.

Never create placeholder implementations.

---

# Development Rules

Every completed phase must:

- Compile successfully
- Pass tests
- Update README
- Update ROADMAP
- Update CHANGELOG
- Commit changes
- Push to GitHub

Do not continue to the next phase until the current phase is complete.

---

# Definition of Done

MjolnirOS Version 1.0 is complete when:

- Voice assistant works locally
- Wake word works
- Memory works
- Windows automation works
- Browser automation works
- GitHub integration works
- Coding agent works
- Plugin marketplace works
- Installer works
- Auto startup works
- Documentation is complete
- All tests pass

This document is the highest priority specification for the project.

All future implementation decisions must conform to this specification.