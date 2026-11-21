"""In-process registration boundary for identities authenticated elsewhere."""

from __future__ import annotations

from datetime import UTC, datetime
from threading import RLock
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.app.domain.device import DeviceIdentity, DeviceStatus


class DeviceNotFound(LookupError):
    pass


class DeviceRevoked(PermissionError):
    pass


class RegisteredDevice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    identity: DeviceIdentity
    status: DeviceStatus = DeviceStatus.ACTIVE
    revoked_at: datetime | None = None


class DeviceRegistry:
    """Register/revoke device identities without minting transport credentials."""

    def __init__(self) -> None:
        self._devices: dict[UUID, RegisteredDevice] = {}
        self._lock = RLock()

    def register(self, identity: DeviceIdentity) -> RegisteredDevice:
        with self._lock:
            if identity.device_id in self._devices:
                raise ValueError("Device identity is already registered.")
            device = RegisteredDevice(identity=identity)
            self._devices[identity.device_id] = device
            return device

    def get(self, device_id: UUID) -> RegisteredDevice:
        with self._lock:
            try:
                return self._devices[device_id]
            except KeyError as error:
                raise DeviceNotFound("Device identity is not registered.") from error

    def require_active(self, device_id: UUID) -> RegisteredDevice:
        device = self.get(device_id)
        if device.status is DeviceStatus.REVOKED:
            raise DeviceRevoked("Device identity has been revoked.")
        return device

    def revoke(self, device_id: UUID) -> RegisteredDevice:
        with self._lock:
            device = self.get(device_id)
            revoked = device.model_copy(
                update={"status": DeviceStatus.REVOKED, "revoked_at": datetime.now(UTC)}
            )
            self._devices[device_id] = revoked
            return revoked

    def list_active(self) -> tuple[RegisteredDevice, ...]:
        with self._lock:
            return tuple(
                device
                for device in self._devices.values()
                if device.status is DeviceStatus.ACTIVE
            )
