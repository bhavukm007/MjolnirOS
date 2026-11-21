"""Non-secret device identity fields used by future paired-device transports."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain.capability import DevicePlatform


class DeviceStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


class DeviceIdentity(BaseModel):
    """Public identity only; private keys and reusable bearer tokens are excluded."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    device_id: UUID = Field(default_factory=uuid4)
    display_name: str = Field(min_length=1, max_length=100)
    platform: DevicePlatform
    public_key_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    registered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
