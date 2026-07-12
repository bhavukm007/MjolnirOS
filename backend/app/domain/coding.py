"""Schemas for the local IDE and terminal Coding Agent."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


CodingAction = Literal[
    "open_workspace",
    "open_project",
    "open_folder",
    "open_file",
    "reveal_file",
    "open_terminal",
    "run_command",
    "list_projects",
    "switch_project",
]


class CodingActionRequest(BaseModel):
    """A validated local IDE or terminal action with explicit approval state."""

    action: CodingAction
    path: str | None = Field(default=None, max_length=4096)
    command: str | None = Field(default=None, max_length=12000)
    cwd: str | None = Field(default=None, max_length=4096)
    confirmed: bool = False


class CodingActionResult(BaseModel):
    """Structured, local-only result for each Coding Agent operation."""

    success: bool
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    confirmation_required: bool = False
