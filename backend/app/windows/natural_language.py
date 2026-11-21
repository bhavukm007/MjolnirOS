"""Supported natural-language command mapping for the Windows agent."""
from dataclasses import dataclass
import re

from backend.app.domain.windows import WindowsActionResult
from backend.app.windows.controller import WindowsController


@dataclass(frozen=True)
class WindowsNaturalCommand:
    action: str
    parameters: dict[str, str]


def parse_windows_command(command: str) -> WindowsNaturalCommand | None:
    """Recognize a Windows command without executing it."""
    text = command.strip().lower()
    if re.fullmatch(
        r"(?:(?:show|check|get|display|report|what(?:'s| is)|give me)\s+)?(?:my\s+)?(?:system|computer|pc)\s+(?:health|status|performance)",
        text,
    ):
        return WindowsNaturalCommand("system_info", {})
    file_patterns = (
        (r"^(?:list directory|list files in)\s+(.+)$", "list_directory", ("path",)),
        (r"^read file\s+(.+)$", "read_file", ("path",)),
        (r"^create file\s+(.+)$", "create_file", ("path",)),
        (r"^create directory\s+(.+)$", "create_directory", ("path",)),
        (r"^delete file\s+(.+)$", "delete_file", ("path",)),
        (r"^copy file\s+(.+?)\s+to\s+(.+)$", "copy_file", ("source", "destination")),
        (r"^move file\s+(.+?)\s+to\s+(.+)$", "move_file", ("source", "destination")),
    )
    for pattern, action, keys in file_patterns:
        match = re.fullmatch(pattern, command.strip(), flags=re.IGNORECASE)
        if match:
            values = [value.strip().strip('"') for value in match.groups()]
            return WindowsNaturalCommand(action, dict(zip(keys, values, strict=True)))
    mappings = (
        (text.startswith("open ") and text.endswith(" folder"), "open_folder", {"path": command[5:-7].strip()}),
        (text.startswith("open explorer"), "open_explorer", {}),
        (text.startswith("open task manager"), "open_task_manager", {}),
        (text.startswith("open "), "open_application", {"name": command[5:].strip()}),
        (text.startswith("launch "), "open_application", {"name": command[7:].strip()}),
        (text.startswith("close "), "close_application", {"name": command[6:].strip()}),
        (text.startswith("search for "), "search_files", {"query": command[11:].strip()}),
    )
    return next((WindowsNaturalCommand(action, parameters) for matched, action, parameters in mappings if matched), None)

def execute_natural_command(command: str, controller: WindowsController) -> WindowsActionResult | None:
    """Execute a recognized non-destructive desktop command, if supported."""
    parsed = parse_windows_command(command)
    return controller.execute(parsed.action, parsed.parameters, False) if parsed else None
