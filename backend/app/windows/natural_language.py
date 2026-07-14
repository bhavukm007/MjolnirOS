"""Supported natural-language command mapping for the Windows agent."""
from dataclasses import dataclass

from backend.app.domain.windows import WindowsActionResult
from backend.app.windows.controller import WindowsController


@dataclass(frozen=True)
class WindowsNaturalCommand:
    action: str
    parameters: dict[str, str]


def parse_windows_command(command: str) -> WindowsNaturalCommand | None:
    """Recognize a Windows command without executing it."""
    text = command.strip().lower()
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
