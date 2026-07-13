"""REST boundary for OAuth-backed productivity plugins."""

from __future__ import annotations

from fastapi import APIRouter, File, Response, UploadFile, status

from backend.app.core.responses import ApiResponse
from backend.app.core.settings import get_settings
from backend.app.domain.productivity import (
    CalendarEventCreate,
    CalendarEventUpdate,
    ConnectionStatus,
    DriveFolderCreate,
    DriveMoveRequest,
    EmailDraftCreate,
    MeetingNotesCreate,
    NotionPageCreate,
    NotionPageUpdate,
    ProductivityProvider,
    SendConfirmation,
)
from backend.app.productivity.productivity_service import ProductivityService

router = APIRouter(prefix="/productivity", tags=["productivity", "plugins"])


def _service() -> ProductivityService:
    return ProductivityService(get_settings())


@router.get("/connections", response_model=ApiResponse[list[ConnectionStatus]])
def connections() -> ApiResponse[list[ConnectionStatus]]:
    return ApiResponse(
        success=True,
        message="Productivity connections loaded.",
        data=_service().connections(),
    )


@router.post("/oauth/{provider}/authorize", response_model=ApiResponse[dict[str, str]])
def authorize(provider: ProductivityProvider) -> ApiResponse[dict[str, str]]:
    return ApiResponse(
        success=True,
        message="Open the authorization URL to connect.",
        data={"authorization_url": _service().authorization_url(provider)},
    )


@router.get("/oauth/{provider}/callback", response_model=ApiResponse[ConnectionStatus])
def oauth_callback(
    provider: ProductivityProvider, code: str, state: str
) -> ApiResponse[ConnectionStatus]:
    return ApiResponse(
        success=True,
        message="Productivity account connected.",
        data=_service().complete_oauth(provider, code, state),
    )


@router.delete("/connections/{provider}", status_code=status.HTTP_204_NO_CONTENT)
def disconnect(provider: ProductivityProvider) -> Response:
    _service().disconnect(provider)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/connections/{provider}/sync", response_model=ApiResponse[ConnectionStatus]
)
def sync(provider: ProductivityProvider) -> ApiResponse[ConnectionStatus]:
    return ApiResponse(
        success=True,
        message="Productivity plugin synchronized.",
        data=_service().sync(provider),
    )


@router.get("/gmail/inbox", response_model=ApiResponse[list[dict[str, object]]])
def gmail_inbox(query: str | None = None) -> ApiResponse[list[dict[str, object]]]:
    return ApiResponse(
        success=True, message="Inbox loaded.", data=_service().gmail_inbox(query)
    )


@router.get(
    "/gmail/messages/{message_id}", response_model=ApiResponse[dict[str, object]]
)
def gmail_message(message_id: str) -> ApiResponse[dict[str, object]]:
    return ApiResponse(
        success=True, message="Email loaded.", data=_service().gmail_message(message_id)
    )


@router.get("/gmail/summary", response_model=ApiResponse[dict[str, object]])
def gmail_summary() -> ApiResponse[dict[str, object]]:
    return ApiResponse(
        success=True, message="Inbox summarized.", data=_service().gmail_summary()
    )


@router.post(
    "/gmail/drafts",
    response_model=ApiResponse[dict[str, object]],
    status_code=status.HTTP_201_CREATED,
)
def create_draft(payload: EmailDraftCreate) -> ApiResponse[dict[str, object]]:
    return ApiResponse(
        success=True,
        message="Email saved as a draft; it was not sent.",
        data=_service().create_draft(payload),
    )


@router.post(
    "/gmail/messages/{message_id}/reply-draft",
    response_model=ApiResponse[dict[str, object]],
)
def reply_draft(
    message_id: str, payload: dict[str, str]
) -> ApiResponse[dict[str, object]]:
    return ApiResponse(
        success=True,
        message="Reply saved as a draft; it was not sent.",
        data=_service().draft_reply(message_id, payload.get("body", "")),
    )


@router.post(
    "/gmail/drafts/{draft_id}/send", response_model=ApiResponse[dict[str, object]]
)
def send_draft(
    draft_id: str, confirmation: SendConfirmation
) -> ApiResponse[dict[str, object]]:
    return ApiResponse(
        success=True,
        message="Email sent after explicit confirmation.",
        data=_service().send_draft(draft_id, confirmation.confirmed),
    )


@router.get("/calendar/events", response_model=ApiResponse[list[dict[str, object]]])
def calendar_events(
    time_min: str | None = None, time_max: str | None = None, query: str | None = None
) -> ApiResponse[list[dict[str, object]]]:
    return ApiResponse(
        success=True,
        message="Calendar events loaded.",
        data=_service().calendar_events(time_min, time_max, query),
    )


@router.post(
    "/calendar/events",
    response_model=ApiResponse[dict[str, object]],
    status_code=status.HTTP_201_CREATED,
)
def create_event(payload: CalendarEventCreate) -> ApiResponse[dict[str, object]]:
    return ApiResponse(
        success=True,
        message="Calendar event created.",
        data=_service().create_event(payload),
    )


@router.put(
    "/calendar/events/{event_id}", response_model=ApiResponse[dict[str, object]]
)
def update_event(
    event_id: str, payload: CalendarEventUpdate
) -> ApiResponse[dict[str, object]]:
    return ApiResponse(
        success=True,
        message="Calendar event updated.",
        data=_service().update_event(event_id, payload),
    )


@router.delete("/calendar/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(event_id: str) -> Response:
    _service().delete_event(event_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/notion/pages/{page_id}", response_model=ApiResponse[dict[str, object]])
def notion_page(page_id: str) -> ApiResponse[dict[str, object]]:
    return ApiResponse(
        success=True,
        message="Notion page loaded.",
        data=_service().notion_page(page_id),
    )


@router.get("/notion/search", response_model=ApiResponse[list[dict[str, object]]])
def notion_search(query: str) -> ApiResponse[list[dict[str, object]]]:
    return ApiResponse(
        success=True,
        message="Notion pages loaded.",
        data=_service().notion_search(query),
    )


@router.post(
    "/notion/pages",
    response_model=ApiResponse[dict[str, object]],
    status_code=status.HTTP_201_CREATED,
)
def notion_create(payload: NotionPageCreate) -> ApiResponse[dict[str, object]]:
    return ApiResponse(
        success=True,
        message="Notion page created.",
        data=_service().notion_create(payload),
    )


@router.post(
    "/notion/meeting-notes",
    response_model=ApiResponse[dict[str, object]],
    status_code=status.HTTP_201_CREATED,
)
def notion_meeting_notes(
    payload: MeetingNotesCreate,
) -> ApiResponse[dict[str, object]]:
    """Create an organized Notion meeting-notes page."""
    return ApiResponse(
        success=True,
        message="Notion meeting notes created.",
        data=_service().notion_meeting_notes(payload),
    )


@router.patch("/notion/pages/{page_id}", response_model=ApiResponse[dict[str, object]])
def notion_update(
    page_id: str, payload: NotionPageUpdate
) -> ApiResponse[dict[str, object]]:
    return ApiResponse(
        success=True,
        message="Notion page updated.",
        data=_service().notion_update(page_id, payload),
    )


@router.post(
    "/drive/files",
    response_model=ApiResponse[dict[str, object]],
    status_code=status.HTTP_201_CREATED,
)
async def drive_upload(
    file: UploadFile = File(...), parent_id: str | None = None
) -> ApiResponse[dict[str, object]]:
    return ApiResponse(
        success=True,
        message="File uploaded to Google Drive.",
        data=await _service().drive_upload(file, parent_id),
    )


@router.get("/drive/files", response_model=ApiResponse[list[dict[str, object]]])
def drive_search(query: str) -> ApiResponse[list[dict[str, object]]]:
    return ApiResponse(
        success=True, message="Drive files loaded.", data=_service().drive_search(query)
    )


@router.get("/drive/files/{file_id}/download")
def drive_download(file_id: str) -> Response:
    return Response(
        content=_service().drive_download(file_id),
        media_type="application/octet-stream",
    )


@router.get("/drive/folders", response_model=ApiResponse[list[dict[str, object]]])
def drive_folders() -> ApiResponse[list[dict[str, object]]]:
    return ApiResponse(
        success=True, message="Drive folders loaded.", data=_service().drive_folders()
    )


@router.post(
    "/drive/folders",
    response_model=ApiResponse[dict[str, object]],
    status_code=status.HTTP_201_CREATED,
)
def drive_folder_create(
    payload: DriveFolderCreate,
) -> ApiResponse[dict[str, object]]:
    return ApiResponse(
        success=True,
        message="Drive folder created.",
        data=_service().drive_folder_create(payload),
    )


@router.post(
    "/drive/files/{file_id}/move", response_model=ApiResponse[dict[str, object]]
)
def drive_move(
    file_id: str, payload: DriveMoveRequest
) -> ApiResponse[dict[str, object]]:
    return ApiResponse(
        success=True,
        message="Drive file moved.",
        data=_service().drive_move(file_id, payload.folder_id),
    )


@router.delete("/drive/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def drive_delete(file_id: str, confirmation: SendConfirmation) -> Response:
    _service().drive_delete(file_id, confirmation.confirmed)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
