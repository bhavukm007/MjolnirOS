"""Safe, local Windows desktop control implementation."""
from __future__ import annotations
import logging, os, shutil, subprocess
from datetime import UTC, datetime
from pathlib import Path
import psutil, pyperclip
from PIL import ImageGrab
from backend.app.core.settings import AppSettings
from backend.app.domain.windows import WindowsActionResult

class WindowsController:
    """Execute supported Windows actions and report structured local results."""
    _DESTRUCTIVE = {"delete_file", "empty_recycle_bin"}
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
        subprocess.Popen([name], shell=False); return WindowsActionResult(success=True,message=f"Opened {name}.")
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
