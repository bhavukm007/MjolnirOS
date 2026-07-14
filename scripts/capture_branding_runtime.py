"""Capture Electron renderer and Windows shell branding evidence."""

import base64
import ctypes
import json
import time
from pathlib import Path
from urllib.request import urlopen

from PIL import ImageGrab
import websocket


OUTPUT = Path(__file__).resolve().parents[1] / "artifacts" / "branding-verification"


def capture_renderer() -> None:
    pages = json.load(urlopen("http://127.0.0.1:9222/json/list", timeout=5))
    page = next(item for item in pages if item.get("type") == "page")
    connection = websocket.create_connection(
        page["webSocketDebuggerUrl"], suppress_origin=True, timeout=30
    )
    try:
        connection.send(json.dumps({"id": 1, "method": "Page.captureScreenshot", "params": {"format": "png"}}))
        response = json.loads(connection.recv())
    finally:
        connection.close()
    (OUTPUT / "main-window.png").write_bytes(base64.b64decode(response["result"]["data"]))


def capture_shell() -> None:
    desktop = ImageGrab.grab(all_screens=True)
    desktop.save(OUTPUT / "desktop-with-taskbar-and-tray.png")
    width, height = desktop.size
    taskbar_height = min(96, height)
    taskbar = desktop.crop((0, height - taskbar_height, width, height))
    taskbar.save(OUTPUT / "taskbar.png")
    # Open Windows' hidden-icons panel; dev builds commonly land there until
    # the user pins their preferred tray icons.
    screen_width = ctypes.windll.user32.GetSystemMetrics(0)
    screen_height = ctypes.windll.user32.GetSystemMetrics(1)
    ctypes.windll.user32.SetCursorPos(screen_width - 322, screen_height - 25)
    ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
    ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(1)
    desktop = ImageGrab.grab(all_screens=True)
    tray_width = min(620, width)
    tray_height = min(620, height)
    tray = desktop.crop((width - tray_width, height - tray_height, width, height))
    tray.save(OUTPUT / "system-tray.png")


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    capture_renderer()
    capture_shell()
    print(OUTPUT)


if __name__ == "__main__":
    main()
