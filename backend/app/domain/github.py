"""Schemas for safe local Git and GitHub operations."""
from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field

GitHubAction = Literal["init", "clone", "status", "add", "commit", "push", "pull", "branch_create", "branch_switch", "merge", "branch_delete", "repository_create", "repository_summary", "issue_create", "pull_request_create"]

class GitHubActionRequest(BaseModel):
    """A structured GitHub Agent request with explicit approval state."""
    action: GitHubAction
    repo_path: str | None = Field(default=None, max_length=4096)
    remote_url: str | None = Field(default=None, max_length=4096)
    paths: list[str] = Field(default_factory=list)
    branch: str | None = Field(default=None, max_length=255)
    message: str | None = Field(default=None, max_length=500)
    owner: str | None = Field(default=None, max_length=255)
    repository: str | None = Field(default=None, max_length=255)
    title: str | None = Field(default=None, max_length=500)
    body: str | None = Field(default=None, max_length=12000)
    base: str | None = Field(default=None, max_length=255)
    head: str | None = Field(default=None, max_length=255)
    visibility: Literal["private", "public"] = "private"
    force: bool = False
    confirmed: bool = False

class GitHubActionResult(BaseModel):
    """Password- and token-safe structured operation result."""
    success: bool
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    confirmation_required: bool = False
