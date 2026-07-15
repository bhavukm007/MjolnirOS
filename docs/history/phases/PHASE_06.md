# Phase 06 - Windows Control Agent

## Objective

Build the Windows Control Agent.

The assistant should safely control the Windows operating system after user approval.

---

## Deliverables

Implement support for:

- Open Applications
- Close Applications
- Focus Applications
- Switch Windows
- Open Explorer
- Open Folders
- Search Files
- Create Files
- Rename Files
- Copy Files
- Move Files
- Delete Files (Permission Required)
- Empty Recycle Bin (Permission Required)

System Information

- CPU Usage
- RAM Usage
- GPU Usage
- Battery
- Disk Usage
- Running Processes
- WiFi
- Bluetooth
- Notifications

Utilities

- Clipboard
- Screenshots
- Task Manager
- Power Options

---

## Requirements

Never execute destructive actions without permission.

Every action should return a success or failure response.

Support natural language commands.

Example:

Mjolnir, open Spotify.

Mjolnir, close Chrome.

Mjolnir, open Downloads folder.

Mjolnir, search for Resume.pdf.

---

## Testing

Verify:

- Applications launch correctly.
- Applications close correctly.
- Folder navigation works.
- File search works.
- CPU/RAM monitoring updates.
- Delete confirmation appears.

---

## Commit

feat(windows): implement Windows control agent

---

## Push

Push changes to GitHub.

Stop.