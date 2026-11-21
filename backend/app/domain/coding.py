"""Schemas for the local IDE and terminal Coding Agent."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

CodingAction = Literal[
    "open_workspace",
    "open_project",
    "open_folder",
    "open_file",
    "reveal_file",
    "open_terminal",
    "run_command",
    "run_project_tests",
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

    @model_validator(mode="after")
    def validate_command_operation(self) -> "CodingActionRequest":
        """Accept only fixed command operations, never arbitrary shell text."""
        if self.action == "run_command" and self.command != "flask run":
            raise ValueError("Only the supported 'flask run' operation is permitted.")
        return self


class CodingActionResult(BaseModel):
    """Structured, local-only result for each Coding Agent operation."""

    success: bool
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    confirmation_required: bool = False
