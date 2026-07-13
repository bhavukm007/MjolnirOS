"""Schemas for local Windows Control Agent operations."""
from typing import Any, Literal
from pydantic import BaseModel, Field
ActionName = Literal["open_application", "close_application", "focus_application", "switch_window", "open_explorer", "open_folder", "search_files", "create_file", "rename_file", "copy_file", "move_file", "delete_file", "empty_recycle_bin", "clipboard_get", "clipboard_set", "screenshot", "open_task_manager", "power", "system_info", "processes", "wifi", "bluetooth", "notifications"]
class WindowsActionRequest(BaseModel):
    """A local Windows action with explicit destructive-action confirmation."""
    action: ActionName
    arguments: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = False
class WindowsActionResult(BaseModel):
    """Structured outcome returned by every Windows action."""
    success: bool
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    confirmation_required: bool = False
