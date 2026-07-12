"""Natural-language mappings for safe Coding Agent commands."""

from __future__ import annotations

from backend.app.domain.coding import CodingActionRequest


def parse_coding_command(command: str) -> CodingActionRequest | None:
    """Map supported typed and voice commands to Coding Agent requests."""
    original = command.strip()
    text = original.lower().removeprefix("mjolnir,").strip().rstrip(".!?")
    if text in {"list my projects", "list projects", "show my projects"}:
        return CodingActionRequest(action="list_projects")
    if text in {"open terminal", "open integrated terminal"}:
        return CodingActionRequest(action="open_terminal", path=".")
    if text.startswith("open this project in vs code"):
        return CodingActionRequest(action="open_project", path=".")
    if text.startswith("run my flask app"):
        return CodingActionRequest(action="run_command", command="flask run")
    return None
