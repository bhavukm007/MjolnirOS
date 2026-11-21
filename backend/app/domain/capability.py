"""Versionable metadata shared by capability providers and policy checks."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PermissionLevel(StrEnum):
    READ = "read"
    OPERATE = "operate"
    MODIFY = "modify"
    SENSITIVE = "sensitive"


class DevicePlatform(StrEnum):
    WINDOWS = "windows"
    ANDROID = "android"


class CapabilityDescriptor(BaseModel):
    """Inspectable capability contract; it does not itself execute code."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    capability_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,127}$")
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1000)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    required_permission: PermissionLevel
    supported_devices: frozenset[DevicePlatform] = Field(min_length=1)
    execution_timeout_seconds: float = Field(default=10, gt=0, le=300)
    requires_confirmation: bool = False
    reversible: bool = True

    @model_validator(mode="after")
    def sensitive_actions_require_confirmation(self) -> CapabilityDescriptor:
        if (
            self.required_permission is PermissionLevel.SENSITIVE
            and not self.requires_confirmation
        ):
            raise ValueError(
                "Sensitive capabilities require exact-action confirmation."
            )
        return self
