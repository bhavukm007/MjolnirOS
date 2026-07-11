const { app, BrowserWindow } = require("electron");
const path = require("node:path");

const FRONTEND_URL = process.env.MJOLNIROS_FRONTEND_URL || "http://localhost:5173";

app.disableHardwareAcceleration();
app.commandLine.appendSwitch("disable-gpu");
app.commandLine.appendSwitch("disable-gpu-compositing");

function isSmokeMode() {
  return process.argv.includes("--smoke");
}

function createWindow() {
  const mainWindow = new BrowserWindow({
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
}

app.whenReady().then(() => {
  if (isSmokeMode()) {
    app.exit(0);
    return;
  }

  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
