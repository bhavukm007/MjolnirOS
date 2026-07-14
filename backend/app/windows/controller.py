"""Safe, local Windows desktop control implementation."""
from __future__ import annotations
import logging, os, shutil, subprocess, time
from datetime import UTC, datetime
from pathlib import Path
import psutil, pyperclip
from PIL import ImageGrab
from backend.app.core.settings import AppSettings
from backend.app.domain.windows import WindowsActionResult

class WindowsController:
    """Execute supported Windows actions and report structured local results."""
    _DESTRUCTIVE = {"delete_file", "empty_recycle_bin"}
    _APPLICATION_ALIASES = {
        "calc": (
            Path(os.environ.get("SystemRoot", "C:\\Windows")) / "System32/calc.exe",
        ),
        "calculator": (
            Path(os.environ.get("SystemRoot", "C:\\Windows")) / "System32/calc.exe",
        ),
        "notepad": (
            Path(os.environ.get("SystemRoot", "C:\\Windows")) / "System32/notepad.exe",
        ),
        "paint": (
            Path(os.environ.get("SystemRoot", "C:\\Windows")) / "System32/mspaint.exe",
        ),
        "file explorer": (
            Path(os.environ.get("SystemRoot", "C:\\Windows")) / "explorer.exe",
        ),
        "explorer": (
            Path(os.environ.get("SystemRoot", "C:\\Windows")) / "explorer.exe",
        ),
        "camera": (),
        "chrome": (
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        ),
        "google chrome": (
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        ),
        "edge": (
            Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Microsoft/Edge/Application/msedge.exe",
        ),
        "microsoft edge": (
            Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Microsoft/Edge/Application/msedge.exe",
        ),
        "firefox": (
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Mozilla Firefox/firefox.exe",
            Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "Mozilla Firefox/firefox.exe",
        ),
        "vs code": (
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Microsoft VS Code/Code.exe",
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Microsoft VS Code/Code.exe",
        ),
        "visual studio code": (
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Microsoft VS Code/Code.exe",
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Microsoft VS Code/Code.exe",
        ),
        "vscode": (
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Microsoft VS Code/Code.exe",
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Microsoft VS Code/Code.exe",
        ),
        "code": (
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Microsoft VS Code/Code.exe",
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Microsoft VS Code/Code.exe",
        ),
        "whatsapp": (
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/WindowsApps/WhatsApp.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/WindowsApps/WhatsAppDesktop.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/WhatsApp/WhatsApp.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "WhatsApp/WhatsApp.exe",
        ),
    }
    _STORE_APPLICATIONS = {
        "calc": "Calculator",
        "calculator": "Calculator",
        "camera": "Camera",
        "paint": "Paint",
        "whatsapp": "WhatsApp",
        "mail": "Mail",
    }
    def __init__(self, settings: AppSettings) -> None: self._settings=settings; self._logger=logging.getLogger(__name__)
    def execute(self, action: str, arguments: dict[str, object], confirmed: bool) -> WindowsActionResult:
        """Execute one local action after enforcing its confirmation policy."""
        if action in self._DESTRUCTIVE and not confirmed: return WindowsActionResult(success=False,message="Explicit confirmation is required.",confirmation_required=True)
        try:
            result=getattr(self, f"_{action}")(**arguments)
            self._logger.info("windows_action_completed",extra={"action":action,"success":result.success})
            return result
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            self._logger.warning("windows_action_failed",extra={"action":action,"error":str(error)})
            return WindowsActionResult(success=False,message=str(error))
    def _open_application(self, name: str) -> WindowsActionResult:
        normalized_name = name.strip().lower()
        self._logger.info(
            "windows_application_resolver_start",
            extra={"requested_name": name, "normalized_name": normalized_name},
        )
        if normalized_name in {"settings", "windows settings"}:
            os.startfile("ms-settings:")
            return WindowsActionResult(
                success=True,
                message=f"Opened {name}.",
                data={"uri": "ms-settings:"},
            )
        candidates = self._APPLICATION_ALIASES.get(normalized_name, ())
        alias_details = [
            {"path": str(path), "exists": path.is_file()} for path in candidates
        ]
        self._logger.info(
            "windows_application_alias_lookup",
            extra={
                "normalized_name": normalized_name,
                "alias_found": normalized_name in self._APPLICATION_ALIASES,
                "candidates": alias_details,
            },
        )
        executable = next((str(path) for path in candidates if path.is_file()), None)
        self._logger.info(
            "windows_application_executable_path",
            extra={"normalized_name": normalized_name, "executable_path": executable},
        )
        path_lookup = None
        if executable is None:
            path_lookup = shutil.which(name) or shutil.which(f"{name}.exe")
            executable = path_lookup
        self._logger.info(
            "windows_application_path_lookup",
            extra={"normalized_name": normalized_name, "path_result": path_lookup},
        )
        if executable is None and normalized_name in self._STORE_APPLICATIONS:
            store_name = self._STORE_APPLICATIONS[normalized_name]
            self._logger.info(
                "windows_application_store_lookup",
                extra={"normalized_name": normalized_name, "store_name": store_name},
            )
            app_id = self._windows_store_app_id(store_name)
            self._logger.info(
                "windows_application_aumid_lookup",
                extra={"normalized_name": normalized_name, "app_user_model_id": app_id},
            )
            if app_id:
                command = ["explorer.exe", f"shell:AppsFolder\\{app_id}"]
                launch = self._launch_application(command, normalized_name)
                return WindowsActionResult(success=True,message=f"Opened {name}.", data=launch)
        if executable is None:
            self._logger.error(
                "windows_application_resolution_failed",
                extra={
                    "normalized_name": normalized_name,
                    "windows_error_code": None,
                },
            )
            raise ValueError(f"Application is not installed or cannot be resolved: {name}.")
        launch = self._launch_application([executable], normalized_name)
        return WindowsActionResult(success=True,message=f"Opened {name}.", data=launch)
    def _windows_store_app_id(self, display_name: str) -> str | None:
        script = (
            f"$start=Get-StartApps | Where-Object {{$_.Name -like '*{display_name}*'}} | Select-Object -First 1; "
            "if($start){$start.AppID; exit 0}; "
            f"$package=Get-AppxPackage | Where-Object {{$_.Name -like '*{display_name}*'}} | Select-Object -First 1; "
            "if($package){$manifest=Get-AppxPackageManifest $package; "
            "$application=$manifest.Package.Applications.Application | Select-Object -First 1; "
            "\"$($package.PackageFamilyName)!$($application.Id)\"}"
        )
        command = ["powershell", "-NoProfile", "-Command", script]
        self._logger.info(
            "windows_application_store_command",
            extra={"display_name": display_name, "command": command},
        )
        try:
            completed = subprocess.run(
                command, capture_output=True, text=True, check=True
            )
        except (OSError, subprocess.SubprocessError) as error:
            self._logger.exception(
                "windows_application_store_lookup_failed",
                extra={
                    "display_name": display_name,
                    "windows_error_code": getattr(error, "winerror", None),
                    "return_value": getattr(error, "returncode", None),
                },
            )
            return None
        app_id = completed.stdout.strip()
        self._logger.info(
            "windows_application_store_return",
            extra={
                "display_name": display_name,
                "app_user_model_id": app_id or None,
                "return_value": completed.returncode,
            },
        )
        return app_id or None
    def _launch_application(self, command: list[str], normalized_name: str) -> dict[str, object]:
        self._logger.info(
            "windows_application_launch_command",
            extra={"normalized_name": normalized_name, "command": command},
        )
        try:
            process = subprocess.Popen(command, shell=False)
        except OSError as error:
            self._logger.exception(
                "windows_application_launch_failed",
                extra={
                    "normalized_name": normalized_name,
                    "command": command,
                    "windows_error_code": error.winerror,
                },
            )
            raise
        executable_name = Path(command[0]).stem.lower()
        expected_names = {executable_name}
        if executable_name == "explorer" and len(command) > 1 and command[1].startswith("shell:AppsFolder"):
            expected_names.add(normalized_name.replace(" ", ""))
        deadline = time.monotonic() + 3.0
        return_value: int | None = None
        running: list[dict[str, object]] = []
        while time.monotonic() < deadline:
            return_value = process.poll()
            running = self._matching_processes(expected_names)
            if return_value not in (None, 0):
                break
            if any(item["pid"] == process.pid for item in running):
                break
            if return_value == 0 and running:
                break
            time.sleep(0.1)
        verified = bool(running) and return_value in (None, 0)
        self._logger.info(
            "windows_application_launch_return",
            extra={
                "normalized_name": normalized_name,
                "command": command,
                "process_id": process.pid,
                "return_value": return_value,
                "windows_error_code": 0 if verified else return_value,
                "actual_running_process": running,
                "verified": verified,
            },
        )
        if not verified:
            raise OSError(
                return_value or 1,
                f"Application launch could not be verified: {normalized_name}.",
            )
        return {
            "resolved_executable_path": command[0],
            "launch_command": command,
            "subprocess_return_value": return_value,
            "launcher_process_id": process.pid,
            "windows_error_code": 0,
            "actual_running_process": running,
        }

    @staticmethod
    def _matching_processes(expected_names: set[str]) -> list[dict[str, object]]:
        matches: list[dict[str, object]] = []
        for candidate in psutil.process_iter(["pid", "name", "exe"]):
            try:
                name = (candidate.info.get("name") or "").lower()
                stem = Path(name).stem
                if stem not in expected_names:
                    continue
                matches.append(
                    {
                        "pid": candidate.info["pid"],
                        "name": candidate.info.get("name"),
                        "executable_path": candidate.info.get("exe"),
                        "running": candidate.is_running(),
                    }
                )
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue
        return matches
    def _close_application(self, name: str) -> WindowsActionResult:
        matches=[p for p in psutil.process_iter(["name"]) if p.info["name"] and p.info["name"].lower()==name.lower()]
        if not matches: return WindowsActionResult(success=False,message=f"{name} is not running.")
        for process in matches: process.terminate()
        return WindowsActionResult(success=True,message=f"Closed {name}.",data={"count":len(matches)})
    def _focus_application(self, name: str) -> WindowsActionResult: return self._activate_window(name)
    def _switch_window(self, name: str) -> WindowsActionResult: return self._activate_window(name)
    def _activate_window(self, name: str) -> WindowsActionResult:
        script=f"$p=Get-Process | Where-Object {{$_.MainWindowTitle -like '*{name.replace("'", "''")}*'}} | Select-Object -First 1; if($p){{$p.MainWindowHandle}}"
        handle=subprocess.check_output(["powershell","-NoProfile","-Command",script],text=True).strip()
        if not handle: return WindowsActionResult(success=False,message=f"No window matched {name}.")
        subprocess.run(["powershell","-NoProfile","-Command",f"Add-Type -Name W -Namespace M -MemberDefinition '[DllImport(\"user32.dll\")] public static extern bool SetForegroundWindow(IntPtr hWnd);'; [M.W]::SetForegroundWindow([IntPtr]{handle})"],check=True,capture_output=True)
        return WindowsActionResult(success=True,message=f"Activated {name}.")
    def _open_explorer(self) -> WindowsActionResult: subprocess.Popen(["explorer.exe"]); return WindowsActionResult(success=True,message="Opened Explorer.")
    def _open_folder(self, path: str) -> WindowsActionResult:
        target=Path(path).expanduser();
        if not target.is_dir(): return WindowsActionResult(success=False,message="Folder does not exist.")
        subprocess.Popen(["explorer.exe",str(target)]); return WindowsActionResult(success=True,message="Opened folder.",data={"path":str(target)})
    def _search_files(self, query: str, root: str | None = None) -> WindowsActionResult:
        base=Path(root) if root else self._settings.windows_search_root
        matches=[str(path) for path in base.rglob("*") if query.lower() in path.name.lower()][:100]
        return WindowsActionResult(success=True,message=f"Found {len(matches)} matching files.",data={"files":matches})
    def _create_file(self, path: str, content: str = "") -> WindowsActionResult:
        target=Path(path); target.parent.mkdir(parents=True,exist_ok=True); target.write_text(content,encoding="utf-8"); return WindowsActionResult(success=True,message="File created.",data={"path":str(target)})
    def _rename_file(self, source: str, destination: str) -> WindowsActionResult: Path(source).rename(destination); return WindowsActionResult(success=True,message="File renamed.")
    def _copy_file(self, source: str, destination: str) -> WindowsActionResult: shutil.copy2(source,destination); return WindowsActionResult(success=True,message="File copied.")
    def _move_file(self, source: str, destination: str) -> WindowsActionResult: shutil.move(source,destination); return WindowsActionResult(success=True,message="File moved.")
    def _delete_file(self, path: str) -> WindowsActionResult: Path(path).unlink(); return WindowsActionResult(success=True,message="File deleted.")
    def _empty_recycle_bin(self) -> WindowsActionResult: subprocess.run(["powershell","-NoProfile","-Command","Clear-RecycleBin -Force"],check=True); return WindowsActionResult(success=True,message="Recycle Bin emptied.")
    def _clipboard_get(self) -> WindowsActionResult: return WindowsActionResult(success=True,message="Clipboard read.",data={"text":pyperclip.paste()})
    def _clipboard_set(self, text: str) -> WindowsActionResult: pyperclip.copy(text); return WindowsActionResult(success=True,message="Clipboard updated.")
    def _screenshot(self) -> WindowsActionResult:
        self._settings.windows_screenshot_path.mkdir(parents=True,exist_ok=True); path=self._settings.windows_screenshot_path/f"screenshot-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.png"; ImageGrab.grab().save(path); return WindowsActionResult(success=True,message="Screenshot captured.",data={"path":str(path)})
    def _open_task_manager(self) -> WindowsActionResult: subprocess.Popen(["taskmgr.exe"]); return WindowsActionResult(success=True,message="Opened Task Manager.")
    def _power(self, operation: str) -> WindowsActionResult:
        commands={"sleep":"rundll32.exe powrprof.dll,SetSuspendState 0,1,0","lock":"rundll32.exe user32.dll,LockWorkStation"}
        if operation not in commands: return WindowsActionResult(success=False,message="Supported power operations: sleep, lock.")
        subprocess.Popen(commands[operation]); return WindowsActionResult(success=True,message=f"Power operation {operation} started.")
    def _system_info(self) -> WindowsActionResult:
        battery=psutil.sensors_battery(); return WindowsActionResult(success=True,message="System information loaded.",data={"cpu_percent":psutil.cpu_percent(interval=0.1),"ram_percent":psutil.virtual_memory().percent,"disk_percent":psutil.disk_usage(os.environ.get("SystemDrive","C:")+"\\").percent,"battery_percent":battery.percent if battery else None,"gpu":[]})
    def _processes(self) -> WindowsActionResult: return WindowsActionResult(success=True,message="Processes loaded.",data={"processes":[{"pid":p.pid,"name":p.info["name"]} for p in psutil.process_iter(["name"])]})
    def _wifi(self) -> WindowsActionResult: return WindowsActionResult(success=True,message="WiFi information loaded.",data={"output":subprocess.getoutput("netsh wlan show interfaces")})
    def _bluetooth(self) -> WindowsActionResult: return WindowsActionResult(success=True,message="Bluetooth information loaded.",data={"output":subprocess.getoutput("powershell -NoProfile -Command Get-PnpDevice -Class Bluetooth")})
    def _notifications(self) -> WindowsActionResult: return WindowsActionResult(success=True,message="Windows notifications are managed by the operating system.",data={})
