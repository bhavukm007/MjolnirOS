"""Schemas for the local Build and Project Agent."""
from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field

BuildAction = Literal["docker_build", "docker_run", "docker_stop", "docker_logs", "docker_list", "install_dependencies", "generate_project", "build_project", "run_project", "register_project"]
BuildLanguage = Literal["python", "flask", "fastapi", "cpp", "java", "javascript", "sql"]
PackageManager = Literal["pip", "npm", "maven", "gradle"]

class BuildActionRequest(BaseModel):
    """Validated local build, package, Docker, or project request."""
    action: BuildAction
    path: str | None = Field(default=None, max_length=4096)
    language: BuildLanguage | None = None
    project_name: str | None = Field(default=None, pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
    package_manager: PackageManager | None = None
    image: str | None = Field(default=None, max_length=512)
    container: str | None = Field(default=None, max_length=512)
    command: str | None = Field(default=None, max_length=12000)
    global_install: bool = False
    privileged: bool = False
    confirmed: bool = False

class BuildActionResult(BaseModel):
    """Structured local Build and Project Agent result."""
    success: bool
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    confirmation_required: bool = False
