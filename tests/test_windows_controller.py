from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from backend.app.windows.controller import WindowsController
from backend.app.windows.natural_language import execute_natural_command


def test_builtin_calculator_alias_resolves_without_changing_existing_fallbacks() -> None:
    controller = WindowsController(SimpleNamespace())

    with (
        patch("pathlib.Path.is_file", return_value=True),
        patch("backend.app.windows.controller.subprocess.Popen") as popen,
        patch.object(
            controller,
            "_matching_processes",
            return_value=[{"pid": popen.return_value.pid, "running": True}],
        ),
    ):
        popen.return_value.poll.return_value = None
        result = controller._open_application("calculator")

    assert result.success
    assert popen.call_args.args[0][0].lower().endswith("calc.exe")


def test_whatsapp_store_alias_is_supported() -> None:
    candidates = WindowsController._APPLICATION_ALIASES["whatsapp"]

    assert any(path.name == "WhatsApp.exe" for path in candidates)
    assert any("WindowsApps" in path.parts for path in candidates)


def test_whatsapp_can_launch_from_windows_store_app_id() -> None:
    controller = WindowsController(SimpleNamespace())

    with (
        patch("pathlib.Path.is_file", return_value=False),
        patch("backend.app.windows.controller.shutil.which", return_value=None),
        patch.object(controller, "_windows_store_app_id", return_value="WhatsApp.Package!App"),
        patch("backend.app.windows.controller.subprocess.Popen") as popen,
        patch.object(
            controller,
            "_matching_processes",
            return_value=[{"pid": popen.return_value.pid, "running": True}],
        ),
    ):
        popen.return_value.poll.return_value = None
        result = controller._open_application("whatsapp")

    assert result.success
    assert popen.call_args.args[0] == [
        "explorer.exe",
        "shell:AppsFolder\\WhatsApp.Package!App",
    ]


def test_camera_uses_same_store_app_id_resolution() -> None:
    controller = WindowsController(SimpleNamespace())

    with (
        patch.object(controller, "_windows_store_app_id", return_value="Camera.Package!App") as lookup,
        patch("backend.app.windows.controller.subprocess.Popen") as popen,
        patch.object(
            controller,
            "_matching_processes",
            return_value=[{"pid": popen.return_value.pid, "running": True}],
        ),
    ):
        popen.return_value.poll.return_value = None
        result = controller._open_application("camera")

    assert result.success
    lookup.assert_called_once_with("Camera")
    assert popen.call_args.args[0] == [
        "explorer.exe",
        "shell:AppsFolder\\Camera.Package!App",
    ]


def test_paint_falls_back_to_windows_store_app_id_when_legacy_executable_is_absent() -> None:
    controller = WindowsController(SimpleNamespace())

    with (
        patch("pathlib.Path.is_file", return_value=False),
        patch("backend.app.windows.controller.shutil.which", return_value=None),
        patch.object(controller, "_windows_store_app_id", return_value="Paint.Package!App") as lookup,
        patch("backend.app.windows.controller.subprocess.Popen") as popen,
        patch.object(
            controller,
            "_matching_processes",
            return_value=[{"pid": popen.return_value.pid, "running": True}],
        ),
    ):
        popen.return_value.poll.return_value = None
        result = controller._open_application("paint")

    assert result.success
    lookup.assert_called_once_with("Paint")
    assert popen.call_args.args[0] == [
        "explorer.exe",
        "shell:AppsFolder\\Paint.Package!App",
    ]


def test_all_vscode_aliases_resolve_to_code_executable() -> None:
    for alias in ("vscode", "vs code", "visual studio code", "code"):
        assert any(path.name == "Code.exe" for path in WindowsController._APPLICATION_ALIASES[alias])


def test_expected_windows_application_aliases_are_registered() -> None:
    for alias in ("calculator", "notepad", "paint", "file explorer"):
        assert alias in WindowsController._APPLICATION_ALIASES


def test_launch_verb_routes_to_application_controller() -> None:
    controller = SimpleNamespace(execute=Mock())
    controller.execute.return_value = SimpleNamespace(success=False)

    result = execute_natural_command("Launch nonexistentapp12345", controller)

    assert result is controller.execute.return_value
    controller.execute.assert_called_once_with(
        "open_application", {"name": "nonexistentapp12345"}, False
    )


def test_launcher_rejects_process_that_exits_without_running_target() -> None:
    controller = WindowsController(SimpleNamespace())

    with (
        patch("backend.app.windows.controller.subprocess.Popen") as popen,
        patch.object(controller, "_matching_processes", return_value=[]),
    ):
        popen.return_value.pid = 1234
        popen.return_value.poll.return_value = 1
        with pytest.raises(OSError, match="could not be verified"):
            controller._launch_application(["missing.exe"], "missing")
