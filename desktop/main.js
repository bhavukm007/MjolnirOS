const { app, BrowserWindow, ipcMain, Menu, Tray, nativeImage, powerMonitor, screen } = require("electron");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");

const FRONTEND_URL = process.env.MJOLNIROS_FRONTEND_URL || "http://localhost:5173";
const BACKEND_HEALTH_URL = "http://127.0.0.1:8000/api/v1/health";
const VOICE_SHUTDOWN_TIMEOUT_MS = 5000;
const APP_ICON_PATH = path.join(__dirname, "..", "assets", "branding", "mjolnir.ico");
const TRAY_ICON_PATH = path.join(__dirname, "..", "assets", "branding", "mjolnir-tray-24.png");
let mainWindow;
let tray;
let minimizeToTray = true;
let backendProcess;
let ownsBackend = false;
let quitPrepared = false;
let quitPreparation;
let listeningEnabled = true;
let listeningBeforeSuspend = false;
let assistantState = "idle";
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
const WINDOW_STATE_PATH = path.join(runtimeDataPath, "desktop-state.json");
app.setPath("userData", runtimeDataPath);
app.setPath("sessionData", path.join(runtimeDataPath, "session"));
app.setAppUserModelId("com.mjolniros.desktop");

function loadDesktopState() {
  try { return JSON.parse(fs.readFileSync(WINDOW_STATE_PATH, "utf8")); }
  catch { return { bounds: { width: 1240, height: 820 }, maximized: false, lastView: "dashboard", startupInitialized: false }; }
}

let desktopState = loadDesktopState();

function saveDesktopState(patch = {}) {
  desktopState = { ...desktopState, ...patch };
  try { fs.writeFileSync(WINDOW_STATE_PATH, JSON.stringify(desktopState, null, 2), "utf8"); }
  catch (error) { console.error(`[desktop] Failed to persist state: ${error.message}`); }
}

function restoredBounds() {
  const bounds = desktopState.bounds;
  if (!bounds || !Number.isFinite(bounds.width) || !Number.isFinite(bounds.height)) return { width: 1240, height: 820 };
  const visible = screen.getAllDisplays().some(({ workArea }) => bounds.x < workArea.x + workArea.width && bounds.x + bounds.width > workArea.x && bounds.y < workArea.y + workArea.height && bounds.y + bounds.height > workArea.y);
  return visible ? bounds : { width: Math.min(bounds.width, 1240), height: Math.min(bounds.height, 820) };
}

function isSmokeMode() {
  return process.argv.includes("--smoke");
}

function createWindow() {
  const bounds = restoredBounds();
  mainWindow = new BrowserWindow({
    ...bounds,
    minWidth: 960,
    minHeight: 640,
    backgroundColor: "#090b10",
    title: "MjolnirOS",
    icon: APP_ICON_PATH,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      // Wake-word capture is an application service. Chromium must not
      // throttle its ScriptProcessor while this window is hidden in the tray.
      backgroundThrottling: false
    }
  });

  if (app.isPackaged) {
    mainWindow.loadFile(path.join(__dirname, "..", "frontend", "dist", "index.html"));
  } else {
    mainWindow.loadURL(FRONTEND_URL);
  }
  mainWindow.webContents.once("did-finish-load", () => { if (desktopState.lastView) mainWindow.webContents.send("navigate", desktopState.lastView); });

  if (desktopState.maximized) mainWindow.maximize();
  const persistBounds = () => { if (!mainWindow.isMaximized() && !mainWindow.isMinimized()) saveDesktopState({ bounds: mainWindow.getBounds() }); };
  mainWindow.on("resize", persistBounds);
  mainWindow.on("move", persistBounds);
  mainWindow.on("maximize", () => saveDesktopState({ maximized: true }));
  mainWindow.on("unmaximize", () => { saveDesktopState({ maximized: false }); persistBounds(); });

  mainWindow.on("close", (event) => {
    if (minimizeToTray && !app.isQuitting) {
      event.preventDefault();
      void hideMainWindow();
    }
  });
  mainWindow.on("session-end", () => { app.isQuitting = true; void prepareApplicationQuit(); });
}

async function runRendererVoice(action) {
  if (!mainWindow || mainWindow.isDestroyed() || mainWindow.webContents.isDestroyed()) return { available: false, listening: false };
  try {
    return await mainWindow.webContents.executeJavaScript(`(async () => { const runtime = window.__mjolnirVoiceRuntime; if (!runtime) return { available: false, listening: false }; const wasListening = Boolean(runtime.listeningEnabled); await runtime.${action}(); return { available: true, wasListening, listening: Boolean(runtime.listeningEnabled) }; })()`, true);
  } catch (error) {
    console.error(`[voice] Renderer ${action} failed: ${error.message}`);
    return { available: false, listening: false };
  }
}

async function hideMainWindow() {
  const result = await runRendererVoice("pause");
  if (result.available) listeningEnabled = result.wasListening;
  updateTray("paused");
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.hide();
}

async function showMainWindow(view) {
  if (!mainWindow || mainWindow.isDestroyed()) createWindow();
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.show();
  mainWindow.focus();
  if (view) mainWindow.webContents.send("navigate", view);
  if (listeningEnabled) await runRendererVoice("resume");
  updateTray(listeningEnabled ? "listening" : "paused");
}

async function pauseListening() {
  listeningEnabled = false;
  await runRendererVoice("pause");
  updateTray("paused");
}

async function resumeListening() {
  listeningEnabled = true;
  if (mainWindow?.isVisible()) {
    await runRendererVoice("resume");
    updateTray("listening");
  } else updateTray("paused");
}

function trayMenu() {
  return Menu.buildFromTemplate([
    { label: "Open Mjolnir", click: () => { void showMainWindow(); } },
    { type: "separator" },
    { label: "Pause Listening", enabled: listeningEnabled, click: () => { void pauseListening(); } },
    { label: "Resume Listening", enabled: !listeningEnabled, click: () => { void resumeListening(); } },
    { type: "separator" },
    { label: "Settings", click: () => { void showMainWindow("settings"); } },
    { label: "Restart Backend", click: () => { void restartBackend(); } },
    { type: "separator" },
    { label: "Quit Mjolnir", click: () => { app.isQuitting = true; void prepareApplicationQuit(); } }
  ]);
}

function updateTray(state = assistantState) {
  assistantState = state;
  if (!tray || tray.isDestroyed()) return;
  tray.setToolTip(`MjolnirOS · ${state.replaceAll("-", " ")}`);
  tray.setContextMenu(trayMenu());
}

function createTray() {
  const icon = nativeImage.createFromPath(TRAY_ICON_PATH);
  tray = new Tray(icon);
  updateTray("listening");
  tray.on("double-click", () => { void showMainWindow(); });
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

async function stopBackend() {
  if (!ownsBackend || !backendProcess || backendProcess.killed) return;
  const processToStop = backendProcess;
  await new Promise((resolve) => { processToStop.once("exit", resolve); processToStop.kill(); });
  if (backendProcess === processToStop) backendProcess = undefined;
  ownsBackend = false;
}

async function restartBackend() {
  if (!ownsBackend || !backendProcess) {
    console.log("[launcher] Restart skipped because Electron does not own the active backend.");
    updateTray("online");
    return;
  }
  updateTray("offline");
  await stopBackend();
  try { await startBackend(); updateTray("online"); }
  catch (error) { console.error(`[launcher] Backend restart failed: ${error.message}`); updateTray("error"); }
}

async function stopVoiceRuntime() {
  if (!mainWindow || mainWindow.isDestroyed() || mainWindow.webContents.isDestroyed()) return;
  const shutdown = mainWindow.webContents.executeJavaScript(
    "window.__mjolnirVoiceRuntime?.stop()",
    true
  );
  let timeoutId;
  const timeout = new Promise((_, reject) => {
    timeoutId = setTimeout(() => reject(new Error("Voice runtime shutdown timed out.")), VOICE_SHUTDOWN_TIMEOUT_MS);
  });
  try {
    await Promise.race([shutdown, timeout]);
    console.log("[voice] Renderer microphone resources released before quit.");
  } catch (error) {
    console.error(`[voice] Graceful renderer shutdown failed: ${error.message}`);
  } finally {
    clearTimeout(timeoutId);
  }
}

function prepareApplicationQuit() {
  if (quitPreparation) return quitPreparation;
  quitPreparation = (async () => {
    await stopVoiceRuntime();
    await stopBackend();
    quitPrepared = true;
    app.quit();
  })();
  return quitPreparation;
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
      let settings = body.data;
      if (!desktopState.startupInitialized) {
        const update = await fetch("http://127.0.0.1:8000/api/v1/settings/user", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ start_with_windows: true }) });
        const updatedBody = await update.json();
        if (updatedBody.success) settings = updatedBody.data;
        saveDesktopState({ startupInitialized: true });
      }
      applyDesktopSettings(settings);
      if (settings.launch_minimized) void hideMainWindow();
    }
  } catch {
    app.setLoginItemSettings({ openAtLogin: true, openAsHidden: false });
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
  ipcMain.on("navigation-state", (_event, view) => { if (typeof view === "string") saveDesktopState({ lastView: view }); });
  ipcMain.on("assistant-state", (_event, state) => { if (typeof state === "string" && listeningEnabled && mainWindow?.isVisible()) updateTray(state); });
  powerMonitor.on("suspend", () => {
    listeningBeforeSuspend = listeningEnabled;
    if (listeningBeforeSuspend) void runRendererVoice("pause");
    updateTray("paused");
  });
  powerMonitor.on("resume", () => {
    if (listeningBeforeSuspend && mainWindow?.isVisible()) void runRendererVoice("resume").then(() => updateTray("listening"));
    listeningBeforeSuspend = false;
  });
  powerMonitor.on("shutdown", (event) => { event.preventDefault(); app.isQuitting = true; void prepareApplicationQuit(); });
  configureLoginItem();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    } else void showMainWindow();
  });
}

if (!ownsApplicationInstance) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (!mainWindow) return;
    void showMainWindow();
  });
  app.whenReady().then(startApplication);
}

app.on("window-all-closed", () => {
  // The tray owns the background runtime; Quit is always explicit.
});

app.on("before-quit", (event) => {
  app.isQuitting = true;
  if (!quitPrepared) {
    event.preventDefault();
    void prepareApplicationQuit();
    return;
  }
});
