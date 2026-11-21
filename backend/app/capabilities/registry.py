"""Typed capability registry with mandatory device and permission checks."""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from time import monotonic
from typing import Any, Awaitable, Callable
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.app.devices.registry import DeviceRegistry
from backend.app.domain.capability import (
    CapabilityDescriptor,
    DevicePlatform,
    PermissionLevel,
)
from backend.app.permissions.engine import ExactActionApproval, PermissionEngine


class CapabilityExecutionError(RuntimeError):
    """Safe, content-free failure classification for an execution attempt."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class CapabilityDefinition:
    descriptor: CapabilityDescriptor
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Callable[[BaseModel], BaseModel | dict[str, Any] | Awaitable[Any]]

    @classmethod
    def create(
        cls,
        *,
        capability_id: str,
        name: str,
        description: str,
        input_model: type[BaseModel],
        output_model: type[BaseModel],
        required_permission: PermissionLevel,
        supported_devices: frozenset[DevicePlatform],
        handler: Callable[[BaseModel], BaseModel | dict[str, Any] | Awaitable[Any]],
        execution_timeout_seconds: float = 10,
        requires_confirmation: bool = False,
        reversible: bool = True,
    ) -> CapabilityDefinition:
        descriptor = CapabilityDescriptor(
            capability_id=capability_id,
            name=name,
            description=description,
            input_schema=input_model.model_json_schema(),
            output_schema=output_model.model_json_schema(),
            required_permission=required_permission,
            supported_devices=supported_devices,
            execution_timeout_seconds=execution_timeout_seconds,
            requires_confirmation=requires_confirmation,
            reversible=reversible,
        )
        return cls(descriptor, input_model, output_model, handler)


class CapabilityExecutionContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    device_id: UUID
    scope: str = Field(min_length=1, max_length=128)
    approval: ExactActionApproval | None = None


class CapabilityRunResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    capability_id: str
    device_id: UUID
    output: dict[str, Any]
    elapsed_ms: int = Field(ge=0)


class CapabilityRegistry:
    """Register capability contracts and make permission checks unavoidable."""

    def __init__(
        self,
        *,
        devices: DeviceRegistry,
        permissions: PermissionEngine,
    ) -> None:
        self._devices = devices
        self._permissions = permissions
        self._definitions: dict[str, CapabilityDefinition] = {}

    def register(self, definition: CapabilityDefinition) -> None:
        capability_id = definition.descriptor.capability_id
        if capability_id in self._definitions:
            raise ValueError(f"Capability '{capability_id}' is already registered.")
        self._definitions[capability_id] = definition

    def discover(
        self, *, device_platform: DevicePlatform | None = None
    ) -> tuple[CapabilityDescriptor, ...]:
        definitions = self._definitions.values()
        return tuple(
            definition.descriptor
            for definition in definitions
            if device_platform is None
            or device_platform in definition.descriptor.supported_devices
        )

    def validate_input(self, capability_id: str, raw_input: dict[str, object]) -> dict[str, Any]:
        """Validate a capability payload without authorizing or executing it."""
        definition = self._definitions.get(capability_id)
        if definition is None:
            raise CapabilityExecutionError("capability_not_registered")
        try:
            return definition.input_model.model_validate(raw_input).model_dump(mode="json")
        except ValidationError as error:
            raise CapabilityExecutionError("invalid_input") from error

    async def execute(
        self,
        capability_id: str,
        raw_input: dict[str, object],
        context: CapabilityExecutionContext,
    ) -> CapabilityRunResult:
        definition = self._definitions.get(capability_id)
        if definition is None:
            raise CapabilityExecutionError("capability_not_registered")
        try:
            device = self._devices.require_active(context.device_id)
        except LookupError as error:
            raise CapabilityExecutionError("device_not_registered") from error
        except PermissionError as error:
            raise CapabilityExecutionError("device_revoked") from error
        if device.identity.platform not in definition.descriptor.supported_devices:
            raise CapabilityExecutionError("device_not_supported")
        try:
            validated_input = definition.input_model.model_validate(raw_input)
        except ValidationError as error:
            raise CapabilityExecutionError("invalid_input") from error

        payload = validated_input.model_dump(mode="json")
        self._permissions.authorize(
            definition.descriptor,
            device_id=context.device_id,
            scope=context.scope,
            payload=payload,
            approval=context.approval,
        )

        started = monotonic()
        try:
            if inspect.iscoroutinefunction(definition.handler):
                raw_output = await asyncio.wait_for(
                    definition.handler(validated_input),
                    timeout=definition.descriptor.execution_timeout_seconds,
                )
            else:
                raw_output = await asyncio.wait_for(
                    asyncio.to_thread(definition.handler, validated_input),
                    timeout=definition.descriptor.execution_timeout_seconds,
                )
                if inspect.isawaitable(raw_output):
                    raw_output = await asyncio.wait_for(
                        raw_output,
                        timeout=definition.descriptor.execution_timeout_seconds,
                    )
            output = definition.output_model.model_validate(raw_output)
        except TimeoutError as error:
            raise CapabilityExecutionError("execution_timeout") from error
        except ValidationError as error:
            raise CapabilityExecutionError("invalid_output") from error
        except CapabilityExecutionError:
            raise
        except Exception as error:
            raise CapabilityExecutionError("handler_failed") from error

        return CapabilityRunResult(
            capability_id=capability_id,
            device_id=context.device_id,
            output=output.model_dump(mode="json"),
            elapsed_ms=max(0, round((monotonic() - started) * 1000)),
        )
