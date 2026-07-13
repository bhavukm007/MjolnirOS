"""Secure OAuth orchestration and provider operations for productivity plugins."""

from __future__ import annotations

from base64 import b64decode, b64encode
from datetime import UTC, datetime, timedelta
import ctypes
from ctypes import wintypes
import json
import logging
from pathlib import Path
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from backend.app.core.settings import AppSettings
from backend.app.domain.productivity import (
    CalendarEventCreate,
    CalendarEventUpdate,
    ConnectionStatus,
    DriveFolderCreate,
    EmailDraftCreate,
    NotionPageCreate,
    NotionPageUpdate,
    MeetingNotesCreate,
    ProductivityProvider,
)

logger = logging.getLogger(__name__)
_GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
_NOTION_AUTH = "https://api.notion.com/v1/oauth/authorize"
_NOTION_TOKEN = "https://api.notion.com/v1/oauth/token"
_GOOGLE_SCOPES = " ".join(
    (
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/drive",
    )
)


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


class TokenStore:
    """Store OAuth data protected by the current Windows user's DPAPI key."""

    def __init__(self, directory: Path) -> None:
        self._path = directory / "oauth-tokens.dpapi"

    def load(self) -> dict[str, dict[str, object]]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(
                self._unprotect(b64decode(self._path.read_bytes())).decode()
            )
        except (OSError, ValueError, UnicodeDecodeError) as error:
            raise HTTPException(
                500, "Secure OAuth token storage is unavailable."
            ) from error

    def save(self, value: dict[str, dict[str, object]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        encrypted = b64encode(self._protect(json.dumps(value).encode()))
        temporary = self._path.with_suffix(".tmp")
        temporary.write_bytes(encrypted)
        temporary.replace(self._path)

    @staticmethod
    def _protect(data: bytes) -> bytes:
        if not hasattr(ctypes, "windll"):
            raise HTTPException(503, "Secure token storage requires Windows DPAPI.")
        source = _DataBlob(
            len(data), (ctypes.c_byte * len(data)).from_buffer_copy(data)
        )
        target = _DataBlob()
        if not ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(source), None, None, None, None, 0, ctypes.byref(target)
        ):
            raise HTTPException(500, "Windows could not protect OAuth credentials.")
        try:
            return ctypes.string_at(target.pbData, target.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(target.pbData)

    @staticmethod
    def _unprotect(data: bytes) -> bytes:
        if not hasattr(ctypes, "windll"):
            raise HTTPException(503, "Secure token storage requires Windows DPAPI.")
        source = _DataBlob(
            len(data), (ctypes.c_byte * len(data)).from_buffer_copy(data)
        )
        target = _DataBlob()
        if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(source), None, None, None, None, 0, ctypes.byref(target)
        ):
            raise HTTPException(500, "Windows could not read OAuth credentials.")
        try:
            return ctypes.string_at(target.pbData, target.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(target.pbData)


class ProductivityService:
    """Operate Gmail, Calendar, Notion, and Drive through least-privilege OAuth."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._store = TokenStore(settings.productivity_storage_directory)
        self._drafts_path = (
            settings.productivity_storage_directory / "email-drafts.json"
        )
        self._states_path = (
            settings.productivity_storage_directory / "oauth-states.json"
        )

    def connections(self) -> list[ConnectionStatus]:
        tokens = self._store.load()
        return [
            self._connection(provider, tokens.get(provider.value))
            for provider in ProductivityProvider
        ]

    def authorization_url(self, provider: ProductivityProvider) -> str:
        state = secrets.token_urlsafe(32)
        states = self._load_json(self._states_path)
        states[state] = {
            "provider": provider.value,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._save_json(self._states_path, states)
        if provider is ProductivityProvider.GOOGLE:
            self._require_google_config()
            return (
                _GOOGLE_AUTH
                + "?"
                + urlencode(
                    {
                        "client_id": self._settings.google_oauth_client_id,
                        "redirect_uri": self._settings.google_oauth_redirect_uri,
                        "response_type": "code",
                        "scope": _GOOGLE_SCOPES,
                        "access_type": "offline",
                        "prompt": "consent",
                        "state": state,
                    }
                )
            )
        self._require_notion_config()
        return (
            _NOTION_AUTH
            + "?"
            + urlencode(
                {
                    "client_id": self._settings.notion_oauth_client_id,
                    "redirect_uri": self._settings.notion_oauth_redirect_uri,
                    "response_type": "code",
                    "owner": "user",
                    "state": state,
                }
            )
        )

    def complete_oauth(
        self, provider: ProductivityProvider, code: str, state: str
    ) -> ConnectionStatus:
        states = self._load_json(self._states_path)
        pending = states.pop(state, None)
        self._save_json(self._states_path, states)
        if not pending or pending.get("provider") != provider.value:
            raise HTTPException(400, "OAuth state is invalid or expired.")
        if provider is ProductivityProvider.GOOGLE:
            self._require_google_config()
            payload = {
                "code": code,
                "client_id": self._settings.google_oauth_client_id,
                "client_secret": self._settings.google_oauth_client_secret,
                "redirect_uri": self._settings.google_oauth_redirect_uri,
                "grant_type": "authorization_code",
            }
            token = self._post_token(_GOOGLE_TOKEN, payload)
            account = self._google_profile(token["access_token"])
        else:
            self._require_notion_config()
            token = self._post_token(
                _NOTION_TOKEN,
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self._settings.notion_oauth_redirect_uri,
                },
                basic=(
                    self._settings.notion_oauth_client_id or "",
                    self._settings.notion_oauth_client_secret or "",
                ),
            )
            account = str(
                token.get("workspace_name") or token.get("bot_id") or "Notion workspace"
            )
        token["account_email"] = account
        token["expires_at"] = (
            datetime.now(UTC) + timedelta(seconds=int(token.get("expires_in", 3600)))
        ).isoformat()
        tokens = self._store.load()
        tokens[provider.value] = token
        self._store.save(tokens)
        logger.info("productivity_oauth_connected", extra={"provider": provider.value})
        return self._connection(provider, token)

    def disconnect(self, provider: ProductivityProvider) -> None:
        tokens = self._store.load()
        tokens.pop(provider.value, None)
        self._store.save(tokens)
        logger.info(
            "productivity_oauth_disconnected", extra={"provider": provider.value}
        )

    def sync(self, provider: ProductivityProvider) -> ConnectionStatus:
        self._token(provider)
        token = self._store.load()[provider.value]
        token["last_sync_at"] = datetime.now(UTC).isoformat()
        tokens = self._store.load()
        tokens[provider.value] = token
        self._store.save(tokens)
        return self._connection(provider, token)

    def gmail_inbox(self, query: str | None = None) -> list[dict[str, object]]:
        token = self._token(ProductivityProvider.GOOGLE)
        params = {"maxResults": 20}
        if query:
            params["q"] = query
        response = self._google(
            "GET", "/gmail/v1/users/me/messages", token, params=params
        )
        return [
            self.gmail_message(str(item["id"])) for item in response.get("messages", [])
        ]

    def gmail_message(self, message_id: str) -> dict[str, object]:
        token = self._token(ProductivityProvider.GOOGLE)
        return self._google(
            "GET",
            f"/gmail/v1/users/me/messages/{message_id}",
            token,
            params={"format": "full"},
        )

    def gmail_summary(self) -> dict[str, object]:
        messages = self.gmail_inbox("newer_than:1d")
        subjects = [
            self._header(item, "Subject") or "(no subject)" for item in messages
        ]
        return {
            "count": len(messages),
            "subjects": subjects,
            "summary": f"{len(messages)} email(s) received in the last day.",
        }

    def create_draft(self, payload: EmailDraftCreate) -> dict[str, object]:
        drafts = self._load_json(self._drafts_path)
        draft_id = secrets.token_urlsafe(16)
        drafts[draft_id] = {
            **payload.model_dump(),
            "id": draft_id,
            "status": "draft",
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._save_json(self._drafts_path, drafts)
        logger.info("email_draft_created", extra={"draft_id": draft_id})
        return drafts[draft_id]

    def draft_reply(self, message_id: str, body: str) -> dict[str, object]:
        message = self.gmail_message(message_id)
        recipient = self._header(message, "Reply-To") or self._header(message, "From")
        subject = self._header(message, "Subject") or ""
        return self.create_draft(
            EmailDraftCreate(
                to=[recipient] if recipient else [],
                subject=(
                    subject if subject.lower().startswith("re:") else f"Re: {subject}"
                ),
                body=body,
                reply_to_message_id=message_id,
            )
        )

    def send_draft(self, draft_id: str, confirmed: bool) -> dict[str, object]:
        if not confirmed:
            raise HTTPException(
                409, "Explicit confirmation is required before sending email."
            )
        drafts = self._load_json(self._drafts_path)
        draft = drafts.get(draft_id)
        if not draft:
            raise HTTPException(404, "Email draft was not found.")
        if draft.get("status") == "sent":
            raise HTTPException(409, "Email draft was already sent.")
        import base64

        mime = f"To: {', '.join(draft['to'])}\r\nSubject: {draft['subject']}\r\n\r\n{draft['body']}".encode()
        result = self._google(
            "POST",
            "/gmail/v1/users/me/messages/send",
            self._token(ProductivityProvider.GOOGLE),
            json={"raw": base64.urlsafe_b64encode(mime).decode().rstrip("=")},
        )
        draft["status"] = "sent"
        draft["sent_at"] = datetime.now(UTC).isoformat()
        drafts[draft_id] = draft
        self._save_json(self._drafts_path, drafts)
        logger.info("email_sent_after_confirmation", extra={"draft_id": draft_id})
        return {"draft_id": draft_id, "message_id": result.get("id"), "status": "sent"}

    def calendar_events(
        self,
        time_min: str | None = None,
        time_max: str | None = None,
        query: str | None = None,
    ) -> list[dict[str, object]]:
        params = {"singleEvents": "true", "orderBy": "startTime"}
        if time_min:
            params["timeMin"] = time_min
        if time_max:
            params["timeMax"] = time_max
        if query:
            params["q"] = query
        return self._google(
            "GET",
            "/calendar/v3/calendars/primary/events",
            self._token(ProductivityProvider.GOOGLE),
            params=params,
        ).get("items", [])

    def create_event(self, payload: CalendarEventCreate) -> dict[str, object]:
        if payload.ends_at <= payload.starts_at:
            raise HTTPException(422, "Event end must be after its start.")
        conflicts = self.calendar_events(
            payload.starts_at.isoformat(), payload.ends_at.isoformat()
        )
        if conflicts:
            raise HTTPException(409, "Calendar conflict detected.")
        data = {
            "summary": payload.title,
            "description": payload.description,
            "start": {
                "dateTime": payload.starts_at.isoformat(),
                "timeZone": payload.timezone,
            },
            "end": {
                "dateTime": payload.ends_at.isoformat(),
                "timeZone": payload.timezone,
            },
            "attendees": [{"email": email} for email in payload.attendees],
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": minutes}
                    for minutes in payload.reminder_minutes
                ],
            },
        }
        return self._google(
            "POST",
            "/calendar/v3/calendars/primary/events",
            self._token(ProductivityProvider.GOOGLE),
            json=data,
        )

    def update_event(
        self, event_id: str, payload: CalendarEventUpdate
    ) -> dict[str, object]:
        current = self._google(
            "GET",
            f"/calendar/v3/calendars/primary/events/{event_id}",
            self._token(ProductivityProvider.GOOGLE),
        )
        data = current.copy()
        if payload.title:
            data["summary"] = payload.title
        if payload.description is not None:
            data["description"] = payload.description
        if payload.attendees is not None:
            data["attendees"] = [{"email": email} for email in payload.attendees]
        if payload.starts_at:
            data["start"] = {
                "dateTime": payload.starts_at.isoformat(),
                "timeZone": payload.timezone
                or current.get("start", {}).get("timeZone", "UTC"),
            }
        if payload.ends_at:
            data["end"] = {
                "dateTime": payload.ends_at.isoformat(),
                "timeZone": payload.timezone
                or current.get("end", {}).get("timeZone", "UTC"),
            }
        return self._google(
            "PUT",
            f"/calendar/v3/calendars/primary/events/{event_id}",
            self._token(ProductivityProvider.GOOGLE),
            json=data,
        )

    def delete_event(self, event_id: str) -> None:
        self._google(
            "DELETE",
            f"/calendar/v3/calendars/primary/events/{event_id}",
            self._token(ProductivityProvider.GOOGLE),
        )

    def notion_search(self, query: str) -> list[dict[str, object]]:
        return self._notion("POST", "/v1/search", json={"query": query}).get(
            "results", []
        )

    def notion_page(self, page_id: str) -> dict[str, object]:
        return self._notion("GET", f"/v1/pages/{page_id}")

    def notion_create(self, payload: NotionPageCreate) -> dict[str, object]:
        return self._notion(
            "POST",
            "/v1/pages",
            json={
                "parent": {"page_id": payload.parent_id},
                "properties": {
                    "title": {"title": [{"text": {"content": payload.title}}]}
                },
                "children": self._notion_blocks(payload.content),
            },
        )

    def notion_meeting_notes(self, payload: MeetingNotesCreate) -> dict[str, object]:
        """Create an organized Notion meeting-notes page."""
        return self.notion_create(
            NotionPageCreate(
                parent_id=payload.parent_id,
                title=f"Meeting notes: {payload.title}",
                content=payload.notes,
            )
        )

    def notion_update(
        self, page_id: str, payload: NotionPageUpdate
    ) -> dict[str, object]:
        data = {}
        if payload.title:
            data["properties"] = {
                "title": {"title": [{"text": {"content": payload.title}}]}
            }
        if payload.content is not None:
            data["children"] = self._notion_blocks(payload.content)
        return self._notion("PATCH", f"/v1/pages/{page_id}", json=data)

    async def drive_upload(
        self, file: UploadFile, parent_id: str | None = None
    ) -> dict[str, object]:
        metadata = {"name": file.filename}
        if parent_id:
            metadata["parents"] = [parent_id]
        token = self._token(ProductivityProvider.GOOGLE)
        content = await file.read()
        files = {
            "metadata": (None, json.dumps(metadata), "application/json"),
            "file": (
                file.filename,
                content,
                file.content_type or "application/octet-stream",
            ),
        }
        return await run_in_threadpool(
            self._request,
            "POST",
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
            token,
            files=files,
        )

    def drive_search(self, query: str) -> list[dict[str, object]]:
        return self._google(
            "GET",
            "/drive/v3/files",
            self._token(ProductivityProvider.GOOGLE),
            params={
                "q": f"name contains '{query.replace("'", "\\'")}'",
                "fields": "files(id,name,mimeType,parents,modifiedTime)",
            },
        ).get("files", [])

    def drive_folders(self) -> list[dict[str, object]]:
        return self._google(
            "GET",
            "/drive/v3/files",
            self._token(ProductivityProvider.GOOGLE),
            params={
                "q": "mimeType='application/vnd.google-apps.folder' and trashed=false",
                "fields": "files(id,name,parents)",
            },
        ).get("files", [])

    def drive_folder_create(self, payload: DriveFolderCreate) -> dict[str, object]:
        data = {"name": payload.name, "mimeType": "application/vnd.google-apps.folder"}
        if payload.parent_id:
            data["parents"] = [payload.parent_id]
        return self._google(
            "POST",
            "/drive/v3/files",
            self._token(ProductivityProvider.GOOGLE),
            json=data,
        )

    def drive_move(self, file_id: str, folder_id: str) -> dict[str, object]:
        return self._google(
            "PATCH",
            f"/drive/v3/files/{file_id}",
            self._token(ProductivityProvider.GOOGLE),
            params={"addParents": folder_id, "fields": "id,name,parents"},
        )

    def drive_delete(self, file_id: str, confirmed: bool) -> None:
        if not confirmed:
            raise HTTPException(
                409, "Explicit confirmation is required before deleting a Drive file."
            )
        self._google(
            "DELETE",
            f"/drive/v3/files/{file_id}",
            self._token(ProductivityProvider.GOOGLE),
        )
        logger.info("drive_file_deleted_after_confirmation", extra={"file_id": file_id})

    def drive_download(self, file_id: str) -> bytes:
        token = self._token(ProductivityProvider.GOOGLE)
        response = httpx.get(
            f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media",
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
        self._raise(response)
        return response.content

    def _token(self, provider: ProductivityProvider) -> str:
        tokens = self._store.load()
        token = tokens.get(provider.value)
        if not token:
            raise HTTPException(
                401, f"Connect {provider.value.title()} before using this integration."
            )
        expires_at = datetime.fromisoformat(str(token.get("expires_at")))
        if expires_at <= datetime.now(UTC) + timedelta(seconds=60):
            refresh = token.get("refresh_token")
            if not refresh:
                raise HTTPException(
                    401, "OAuth access expired. Reconnect this provider."
                )
            if provider is not ProductivityProvider.GOOGLE:
                raise HTTPException(
                    401, "OAuth access expired. Reconnect this provider."
                )
            refreshed = self._post_token(
                _GOOGLE_TOKEN,
                {
                    "grant_type": "refresh_token",
                    "refresh_token": refresh,
                    "client_id": self._settings.google_oauth_client_id,
                    "client_secret": self._settings.google_oauth_client_secret,
                },
            )
            token.update(refreshed)
            token["expires_at"] = (
                datetime.now(UTC)
                + timedelta(seconds=int(refreshed.get("expires_in", 3600)))
            ).isoformat()
            tokens[provider.value] = token
            self._store.save(tokens)
            logger.info("oauth_token_refreshed", extra={"provider": provider.value})
        return str(token["access_token"])

    def _google(
        self, method: str, path: str, token: str, **kwargs: object
    ) -> dict[str, object]:
        return self._request(
            method, "https://www.googleapis.com" + path, token, **kwargs
        )

    def _notion(self, method: str, path: str, **kwargs: object) -> dict[str, object]:
        return self._request(
            method,
            "https://api.notion.com" + path,
            self._token(ProductivityProvider.NOTION),
            headers={"Notion-Version": "2022-06-28"},
            **kwargs,
        )

    def _request(
        self,
        method: str,
        url: str,
        token: str,
        headers: dict[str, str] | None = None,
        **kwargs: object,
    ) -> dict[str, object]:
        response = httpx.request(
            method,
            url,
            headers={"Authorization": f"Bearer {token}", **(headers or {})},
            timeout=20,
            **kwargs,
        )
        self._raise(response)
        return response.json() if response.content else {}

    @staticmethod
    def _raise(response: httpx.Response) -> None:
        if response.is_error:
            raise HTTPException(
                response.status_code,
                "Productivity provider request failed. Reconnect the integration or try again.",
            )

    @staticmethod
    def _header(message: dict[str, object], name: str) -> str | None:
        for item in message.get("payload", {}).get("headers", []):
            if item.get("name", "").lower() == name.lower():
                return item.get("value")
        return None

    @staticmethod
    def _notion_blocks(content: str) -> list[dict[str, object]]:
        return [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": line}}]
                },
            }
            for line in content.splitlines()
            if line
        ]

    def _connection(
        self, provider: ProductivityProvider, token: dict[str, object] | None
    ) -> ConnectionStatus:
        return ConnectionStatus(
            provider=provider,
            connected=token is not None,
            account_email=str(token.get("account_email")) if token else None,
            expires_at=(
                datetime.fromisoformat(str(token["expires_at"]))
                if token and token.get("expires_at")
                else None
            ),
            last_sync_at=(
                datetime.fromisoformat(str(token["last_sync_at"]))
                if token and token.get("last_sync_at")
                else None
            ),
        )

    def _post_token(
        self, url: str, data: dict[str, object], basic: tuple[str, str] | None = None
    ) -> dict[str, object]:
        response = httpx.post(url, data=data, auth=basic, timeout=20)
        self._raise(response)
        return response.json()

    def _google_profile(self, token: str) -> str:
        return str(
            self._google("GET", "/oauth2/v2/userinfo", token).get(
                "email", "Google account"
            )
        )

    def _require_google_config(self) -> None:
        if (
            not self._settings.google_oauth_client_id
            or not self._settings.google_oauth_client_secret
        ):
            raise HTTPException(503, "Google OAuth is not configured.")

    def _require_notion_config(self) -> None:
        if (
            not self._settings.notion_oauth_client_id
            or not self._settings.notion_oauth_client_secret
        ):
            raise HTTPException(503, "Notion OAuth is not configured.")

    @staticmethod
    def _load_json(path: Path) -> dict[str, object]:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    @staticmethod
    def _save_json(path: Path, value: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
        temporary.replace(path)
