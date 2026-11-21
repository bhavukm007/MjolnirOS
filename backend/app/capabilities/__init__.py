"""Declarative capability contracts and permission-gated registration."""

from backend.app.capabilities.registry import (
    CapabilityDefinition,
    CapabilityExecutionContext,
    CapabilityExecutionError,
    CapabilityRegistry,
    CapabilityRunResult,
)
from backend.app.domain.capability import (
    CapabilityDescriptor,
    DevicePlatform,
    PermissionLevel,
)

__all__ = [
    "CapabilityDefinition",
    "CapabilityDescriptor",
    "CapabilityExecutionContext",
    "CapabilityExecutionError",
    "CapabilityRegistry",
    "CapabilityRunResult",
    "DevicePlatform",
    "PermissionLevel",
]
