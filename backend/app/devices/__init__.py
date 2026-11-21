"""Device identity and registration primitives."""

from backend.app.devices.registry import (
    DeviceNotFound,
    DeviceRegistry,
    DeviceRevoked,
    RegisteredDevice,
)
from backend.app.domain.device import DeviceIdentity, DeviceStatus

__all__ = [
    "DeviceIdentity",
    "DeviceNotFound",
    "DeviceRegistry",
    "DeviceRevoked",
    "DeviceStatus",
    "RegisteredDevice",
]
