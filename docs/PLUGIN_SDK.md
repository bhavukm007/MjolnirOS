# Plugin SDK

MjolnirOS supports dynamic plugins.

Plugins extend the operating system without modifying core code.

---

# Folder Structure

plugins/

plugin_name/

manifest.json

permissions.json

plugin.py

README.md

---

# Manifest

Contains

- Name
- Version
- Author
- Description
- Entry Point

---

# Permissions

Declare required permissions.

Examples

Browser

Filesystem

Clipboard

Microphone

Camera

Network

GitHub

---

# Plugin Lifecycle

Install

Load

Run

Unload

Remove

---

# Plugin Rules

Plugins must

- Be isolated
- Not modify core files
- Use documented APIs
- Request permissions

## Productivity plugin permissions

Phase 14 adds `oauth`, `email`, `calendar`, `notion`, `drive`, and `filesystem` declarations. Productivity plugins remain isolated entry-point packages; only the core API service handles OAuth tokens. Gmail transmission and Drive deletion require a fresh explicit confirmation and write audit events without credentials or token data.

---

## Communication plugin permissions

Communication plugins use `communication_read` and `communication_send` with `oauth` and `network`. OAuth-backed provider permissions (`email`, `calendar`, `notion`, and `drive`) likewise require `oauth` and `network`; duplicate or incomplete declarations are blocked. Credentials, provider HTTP, confirmations, and audit events remain in the core API boundary. Voice calling is reserved for future support.

# Default Plugins

Spotify

Gmail

Weather

Docker

GitHub

Calendar

Discord

Slack

WhatsApp
