"use strict";

const { app, BrowserWindow, ipcMain, Menu, nativeImage, Tray } = require("electron");
const path = require("node:path");

const { DesktopSettingsStore } = require("./desktop_settings");
const { DesktopLogger } = require("./logger");
const { DesktopRuntime } = require("./runtime");

const FRONTEND_URL = process.env.MJOLNIROS_FRONTEND_URL || "http://127.0.0.1:5173";

app.disableHardwareAcceleration();
app.commandLine.appendSwitch("disable-gpu");
app.commandLine.appendSwitch("disable-gpu-compositing");
app.setName("MjolnirOS");

function isSmokeMode() {
  return process.argv.includes("--smoke");
}

app.whenReady().then(() => {
  if (isSmokeMode()) {
    app.quit();
    return;
  }

  const logger = new DesktopLogger(path.join(app.getPath("logs"), "desktop.log"));
  const settingsStore = new DesktopSettingsStore(
    path.join(app.getPath("userData"), "desktop-settings.json"),
    logger
  );
  const runtime = new DesktopRuntime({
    app,
    BrowserWindow,
    Tray,
    Menu,
    nativeImage,
    ipcMain,
    settingsStore,
    logger,
    frontendUrl: FRONTEND_URL
  });
  runtime.initialize();
});
