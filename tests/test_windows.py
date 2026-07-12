"""Windows Control Agent safety tests."""
from backend.app.core.settings import AppSettings
from backend.app.windows.controller import WindowsController
def test_destructive_actions_require_confirmation(tmp_path) -> None:
    """Deletion is never executed before confirmation."""
    controller=WindowsController(AppSettings(windows_search_root=tmp_path,windows_screenshot_path=tmp_path))
    result=controller.execute("delete_file",{"path":str(tmp_path/"x.txt")},False)
    assert result.confirmation_required is True
def test_file_operations_and_search_are_local(tmp_path) -> None:
    """File creation and discovery return structured local results."""
    controller=WindowsController(AppSettings(windows_search_root=tmp_path,windows_screenshot_path=tmp_path))
    created=controller.execute("create_file",{"path":str(tmp_path/"Resume.pdf"),"content":"local"},False)
    found=controller.execute("search_files",{"query":"resume","root":str(tmp_path)},False)
    assert created.success and found.data["files"]
