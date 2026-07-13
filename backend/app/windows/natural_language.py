"""Supported natural-language command mapping for the Windows agent."""
from backend.app.domain.windows import WindowsActionResult
from backend.app.windows.controller import WindowsController

def execute_natural_command(command: str, controller: WindowsController) -> WindowsActionResult | None:
    """Execute a recognized non-destructive desktop command, if supported."""
    text=command.strip().lower()
    if text.startswith("open ") and text.endswith(" folder"): return controller.execute("open_folder",{"path":command[5:-7].strip()},False)
    if text.startswith("open explorer"): return controller.execute("open_explorer",{},False)
    if text.startswith("open task manager"): return controller.execute("open_task_manager",{},False)
    if text.startswith("open "): return controller.execute("open_application",{"name":command[5:].strip()},False)
    if text.startswith("close "): return controller.execute("close_application",{"name":command[6:].strip()},False)
    if text.startswith("search for "): return controller.execute("search_files",{"query":command[11:].strip()},False)
    return None
