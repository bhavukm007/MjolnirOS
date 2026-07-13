const { app, BrowserWindow, ipcMain, Menu, Tray, nativeImage } = require("electron");
const path = require("node:path");

const FRONTEND_URL = process.env.MJOLNIROS_FRONTEND_URL || "http://localhost:5173";
let mainWindow;
let tray;
let minimizeToTray = true;

app.disableHardwareAcceleration();
app.commandLine.appendSwitch("disable-gpu");
app.commandLine.appendSwitch("disable-gpu-compositing");

function isSmokeMode() {
  return process.argv.includes("--smoke");
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 960,
    minHeight: 640,
    backgroundColor: "#090b10",
    title: "MjolnirOS",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  if (app.isPackaged) {
    mainWindow.loadFile(path.join(__dirname, "..", "frontend", "dist", "index.html"));
  } else {
    mainWindow.loadURL(FRONTEND_URL);
  }

  mainWindow.on("close", (event) => {
    if (minimizeToTray && !app.isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });
}

function createTray() {
  const icon = nativeImage.createFromDataURL("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLJXQAAAABJRU5ErkJggg==");
  tray = new Tray(icon);
  tray.setToolTip("MjolnirOS");
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: "Open", click: () => { mainWindow.show(); mainWindow.focus(); } },
    { label: "Restart", click: () => { app.relaunch(); app.isQuitting = true; app.quit(); } },
    { label: "Settings", click: () => { mainWindow.show(); mainWindow.focus(); } },
    { label: "Quit", click: () => { app.isQuitting = true; app.quit(); } }
  ]));
  tray.on("double-click", () => { mainWindow.show(); mainWindow.focus(); });
}

function applyDesktopSettings(settings) {
  if (!settings || typeof settings !== "object") return;
  minimizeToTray = settings.minimize_to_tray !== false;
  app.setLoginItemSettings({
    openAtLogin: settings.start_with_windows === true,
    openAsHidden: settings.launch_minimized === true
  });
}

async function configureLoginItem() {
  try {
    const response = await fetch("http://127.0.0.1:8000/api/v1/settings/user");
    const body = await response.json();
    if (body.success) {
      applyDesktopSettings(body.data);
      if (body.data.launch_minimized) mainWindow.hide();
    }
  } catch {
    // The backend can start after Electron; retain the previous Windows setting.
  }
}

app.whenReady().then(() => {
  if (isSmokeMode()) {
    app.exit(0);
    return;
  }

  createWindow();
  createTray();
  ipcMain.on("settings-updated", (_event, settings) => applyDesktopSettings(settings));
  configureLoginItem();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  // The tray owns the background runtime; Quit is always explicit.
});
