"""REST API for confirmation-gated communication integrations."""

from fastapi import APIRouter, Response, status

from backend.app.communication.communication_service import CommunicationService
from backend.app.core.responses import ApiResponse
from backend.app.core.settings import get_settings
from backend.app.domain.communication import (
    AuditEvent,
    CommunicationConnection,
    CommunicationProvider,
    CredentialConnect,
    MessageDraft,
    MessageDraftCreate,
    SendMessageConfirmation,
)

router = APIRouter(prefix="/communication", tags=["communication", "plugins"])


def _service() -> CommunicationService:
    return CommunicationService(get_settings())


@router.get("/connections", response_model=ApiResponse[list[CommunicationConnection]])
def connections() -> ApiResponse[list[CommunicationConnection]]:
    return ApiResponse(
        success=True,
        message="Communication connections loaded.",
        data=_service().connections(),
    )


@router.put(
    "/connections/{provider}", response_model=ApiResponse[CommunicationConnection]
)
def connect(
    provider: CommunicationProvider, payload: CredentialConnect
) -> ApiResponse[CommunicationConnection]:
    return ApiResponse(
        success=True,
        message="Communication account connected securely.",
        data=_service().connect(provider, payload),
    )


@router.delete("/connections/{provider}", status_code=status.HTTP_204_NO_CONTENT)
def disconnect(provider: CommunicationProvider) -> Response:
    _service().disconnect(provider)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{provider}/conversations", response_model=ApiResponse[list[dict[str, object]]]
)
def conversations(
    provider: CommunicationProvider,
) -> ApiResponse[list[dict[str, object]]]:
    return ApiResponse(
        success=True,
        message="Conversations loaded.",
        data=_service().conversations(provider),
    )


@router.get("/{provider}/search", response_model=ApiResponse[list[dict[str, object]]])
def search(
    provider: CommunicationProvider, query: str
) -> ApiResponse[list[dict[str, object]]]:
    return ApiResponse(
        success=True,
        message="Communication search completed.",
        data=_service().search(provider, query),
    )


@router.post(
    "/{provider}/drafts",
    response_model=ApiResponse[MessageDraft],
    status_code=status.HTTP_201_CREATED,
)
def create_draft(
    provider: CommunicationProvider, payload: MessageDraftCreate
) -> ApiResponse[MessageDraft]:
    return ApiResponse(
        success=True,
        message="Message saved as a draft; it was not sent.",
        data=_service().create_draft(provider, payload),
    )


@router.post("/drafts/{draft_id}/send", response_model=ApiResponse[MessageDraft])
def send_draft(
    draft_id: str, payload: SendMessageConfirmation
) -> ApiResponse[MessageDraft]:
    return ApiResponse(
        success=True,
        message="Message sent after explicit confirmation.",
        data=_service().send_draft(draft_id, payload.confirmed),
    )


@router.get("/audit/events", response_model=ApiResponse[list[AuditEvent]])
def audit_events() -> ApiResponse[list[AuditEvent]]:
    return ApiResponse(
        success=True, message="Audit events loaded.", data=_service().audit_events()
    )
