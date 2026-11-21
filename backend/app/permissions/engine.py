"""In-process permission policy layered on the existing authenticated API."""

from __future__ import annotations

import hashlib
import json
import time
from threading import RLock
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain.capability import CapabilityDescriptor, PermissionLevel

_LEVEL = {
    PermissionLevel.READ: 1,
    PermissionLevel.OPERATE: 2,
    PermissionLevel.MODIFY: 3,
    PermissionLevel.SENSITIVE: 4,
}


class PermissionDenied(PermissionError):
    pass


class ApprovalRequired(PermissionDenied):
    pass


class PermissionGrant(BaseModel):
    """A revocable grant bound to one device, capability, level, and named scope."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    grant_id: UUID = Field(default_factory=uuid4)
    device_id: UUID
    capability_id: str
    permission: PermissionLevel
    scope: str = Field(
        min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$"
    )
    revoked: bool = False


class ExactActionApproval(BaseModel):
    """One-use confirmation for one canonicalized action payload."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    approval_id: UUID = Field(default_factory=uuid4)
    device_id: UUID
    capability_id: str
    scope: str
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expires_at: float


class PermissionEngine:
    """Evaluate revocable grants and consume exact-action confirmations once."""

    def __init__(self) -> None:
        self._grants: dict[UUID, PermissionGrant] = {}
        self._consumed_approvals: set[UUID] = set()
        self._lock = RLock()

    def grant(
        self,
        *,
        device_id: UUID,
        capability_id: str,
        permission: PermissionLevel,
        scope: str,
        grant_id: UUID | None = None,
    ) -> PermissionGrant:
        grant = PermissionGrant(
            grant_id=grant_id or uuid4(),
            device_id=device_id,
            capability_id=capability_id,
            permission=permission,
            scope=scope,
        )
        with self._lock:
            self._grants[grant.grant_id] = grant
        return grant

    def revoke(self, grant_id: UUID) -> None:
        with self._lock:
            grant = self._grants.get(grant_id)
            if grant is None:
                raise KeyError("Permission grant was not found.")
            self._grants[grant_id] = grant.model_copy(update={"revoked": True})

    def issue_exact_approval(
        self,
        *,
        device_id: UUID,
        capability_id: str,
        scope: str,
        payload: dict[str, object],
        lifetime_seconds: int = 120,
    ) -> ExactActionApproval:
        """Create approval evidence after a trusted local approval interaction.

        No HTTP endpoint exposes this method. The future approval UI must bind
        its confirmation to these exact fields and the short expiry.
        """
        if not 1 <= lifetime_seconds <= 300:
            raise ValueError("Approval lifetime must be between 1 and 300 seconds.")
        return ExactActionApproval(
            device_id=device_id,
            capability_id=capability_id,
            scope=scope,
            payload_sha256=self.payload_digest(payload),
            expires_at=time.time() + lifetime_seconds,
        )

    @staticmethod
    def payload_digest(payload: dict[str, object]) -> str:
        canonical = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def authorize(
        self,
        descriptor: CapabilityDescriptor,
        *,
        device_id: UUID,
        scope: str,
        payload: dict[str, object],
        approval: ExactActionApproval | None = None,
    ) -> None:
        with self._lock:
            permitted = any(
                not grant.revoked
                and grant.device_id == device_id
                and grant.capability_id == descriptor.capability_id
                and grant.scope == scope
                and _LEVEL[grant.permission] >= _LEVEL[descriptor.required_permission]
                for grant in self._grants.values()
            )
            if not permitted:
                raise PermissionDenied(
                    "No active grant covers this device, capability, permission, and scope."
                )

            if descriptor.requires_confirmation:
                self._consume_approval(
                    approval,
                    descriptor=descriptor,
                    device_id=device_id,
                    scope=scope,
                    payload=payload,
                )

    def _consume_approval(
        self,
        approval: ExactActionApproval | None,
        *,
        descriptor: CapabilityDescriptor,
        device_id: UUID,
        scope: str,
        payload: dict[str, object],
    ) -> None:
        if approval is None:
            raise ApprovalRequired(
                "This capability requires approval for its exact action."
            )
        if (
            approval.device_id != device_id
            or approval.capability_id != descriptor.capability_id
            or approval.scope != scope
            or approval.payload_sha256 != self.payload_digest(payload)
            or approval.expires_at <= time.time()
            or approval.approval_id in self._consumed_approvals
        ):
            raise PermissionDenied("Approval does not authorize this exact action.")
        self._consumed_approvals.add(approval.approval_id)
