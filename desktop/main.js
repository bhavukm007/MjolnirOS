const { app, BrowserWindow, ipcMain, Menu, Tray, nativeImage } = require("electron");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");

const FRONTEND_URL = process.env.MJOLNIROS_FRONTEND_URL || "http://localhost:5173";
const BACKEND_HEALTH_URL = "http://127.0.0.1:8000/api/v1/health";
let mainWindow;
let tray;
let minimizeToTray = true;
let backendProcess;
let ownsBackend = false;
const ownsApplicationInstance = app.requestSingleInstanceLock();

app.disableHardwareAcceleration();
app.commandLine.appendSwitch("disable-gpu");
app.commandLine.appendSwitch("disable-gpu-compositing");
app.commandLine.appendSwitch("in-process-gpu");

// Keep Chromium's profile/cache beside the application data.  The default
// profile can be inaccessible when MjolnirOS is launched by a Windows startup
// task or another user context, which prevents its renderer from starting.
const runtimeDataPath = path.join(__dirname, "..", "database", "electron-runtime");
fs.mkdirSync(runtimeDataPath, { recursive: true });
app.setPath("userData", runtimeDataPath);
app.setPath("sessionData", path.join(runtimeDataPath, "session"));

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

function backendIsReady() {
  console.log(`[launcher] Health probe start: ${BACKEND_HEALTH_URL}`);
  return new Promise((resolve) => {
    let settled = false;
    const finish = (ready) => {
      if (!settled) {
        settled = true;
        console.log(`[launcher] Health probe result: ${ready ? "HTTP 200" : "unreachable"}`);
        resolve(ready);
      }
    };
    const request = http.get(BACKEND_HEALTH_URL, (response) => {
      response.resume();
      finish(response.statusCode === 200);
    });
    request.setTimeout(1000, () => request.destroy());
    request.on("error", () => finish(false));
  });
}

function attachBackend(reason) {
  backendProcess = undefined;
  ownsBackend = false;
  console.log(`[launcher] Attach decision: ${reason}; ownership=external`);
}

function pause(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function startBackend() {
  if (await backendIsReady()) {
    attachBackend("health probe succeeded");
    return;
  }

  const projectRoot = path.join(__dirname, "..");
  const python = process.env.MJOLNIROS_PYTHON
    || path.join(projectRoot, ".venv", "Scripts", "python.exe");
  console.log("[launcher] Spawn decision: health probe did not return HTTP 200; ownership=electron");
  backendProcess = spawn(
    python,
    ["-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8000"],
    { cwd: projectRoot, windowsHide: true, stdio: ["ignore", "pipe", "pipe"] }
  );
  ownsBackend = true;
  let exitCode = null;
  let finalProbePromise = null;
  const attachAfterExit = () => {
    if (!finalProbePromise) {
      finalProbePromise = backendIsReady().then((healthy) => {
        if (healthy) attachBackend("spawn exited but final health probe succeeded");
        return healthy;
      });
    }
    return finalProbePromise;
  };
  backendProcess.stdout.on("data", (data) => console.log(`[backend] ${data}`));
  backendProcess.stderr.on("data", (data) => console.error(`[backend] ${data}`));
  backendProcess.on("error", (error) => console.error("[launcher] Failed to start backend:", error));
  backendProcess.on("exit", (code) => {
    exitCode = code;
    console.error(`[launcher] Backend exited with code ${code}; performing final health probe.`);
    void attachAfterExit();
  });

  for (let attempt = 0; attempt < 30; attempt += 1) {
    if (await backendIsReady()) {
      if (backendProcess.exitCode !== null) await attachAfterExit();
      return;
    }
    if (exitCode !== null) {
      // A second launcher can win the port race. Attach to its healthy backend
      // rather than treating WinError 10048 as an Electron startup failure.
      if (await attachAfterExit()) return;
      break;
    }
    await pause(250);
  }
  backendProcess = undefined;
  ownsBackend = false;
  if (exitCode !== null) throw new Error(`Backend exited with code ${exitCode}.`);
  throw new Error("MjolnirOS backend did not become ready on port 8000.");
}

function stopBackend() {
  if (ownsBackend && backendProcess && !backendProcess.killed) backendProcess.kill();
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

async function startApplication() {
  if (isSmokeMode()) {
    app.exit(0);
    return;
  }

  try {
    await startBackend();
  } catch (error) {
    console.error(error);
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
}

if (!ownsApplicationInstance) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (!mainWindow) return;
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.show();
    mainWindow.focus();
  });
  app.whenReady().then(startApplication);
}

app.on("window-all-closed", () => {
  // The tray owns the background runtime; Quit is always explicit.
});

app.on("before-quit", stopBackend);
