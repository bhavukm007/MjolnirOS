"use strict";

const os = require("node:os");
const path = require("node:path");

function createTrayImage(nativeImage) {
  const svg = [
    '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">',
    '<rect width="32" height="32" rx="6" fill="#0b1220"/>',
    '<path d="M9 10h14v5h-2v9h-4v-6h-2v6h-4v-9H9z" fill="#5eead4"/>',
    '<path d="M13 8h6v3h-6z" fill="#f8fafc"/>',
    "</svg>"
  ].join("");
  return nativeImage.createFromDataURL(`data:image/svg+xml;base64,${Buffer.from(svg).toString("base64")}`);
}

function getSystemStatus() {
  const totalMemoryBytes = os.totalmem();
  const freeMemoryBytes = os.freemem();
  const cpuCount = os.cpus().length;

  return {
    cpuCount,
    cpuModel: os.cpus()[0]?.model ?? "Unknown CPU",
    memoryUsedBytes: totalMemoryBytes - freeMemoryBytes,
    memoryTotalBytes: totalMemoryBytes,
    runningAgents: 0,
    uptimeSeconds: Math.floor(os.uptime())
  };
}

class DesktopRuntime {
  constructor({ app, BrowserWindow, Tray, Menu, nativeImage, ipcMain, settingsStore, logger, frontendUrl }) {
    this.app = app;
    this.BrowserWindow = BrowserWindow;
    this.Tray = Tray;
    this.Menu = Menu;
    this.nativeImage = nativeImage;
    this.ipcMain = ipcMain;
    this.settingsStore = settingsStore;
    this.logger = logger;
    this.frontendUrl = frontendUrl;
    this.mainWindow = null;
    this.settingsWindow = null;
    this.tray = null;
    this.isQuitting = false;
    this.settings = null;
  }

  initialize() {
    this.settings = this.settingsStore.load();
    this.applyLoginItemSetting(this.settings.launchOnStartup);
    this.registerIpcHandlers();
    this.createTray();
    this.createMainWindow();
    this.registerLifecycleHandlers();
    this.logger.info("desktop_runtime_started", { launchOnStartup: this.settings.launchOnStartup });
  }

  registerIpcHandlers() {
    this.ipcMain.handle("desktop:get-settings", () => this.settings);
    this.ipcMain.handle("desktop:set-launch-on-startup", (_event, enabled) => this.setLaunchOnStartup(enabled));
    this.ipcMain.handle("desktop:get-system-status", () => getSystemStatus());
    this.ipcMain.handle("desktop:open-settings", () => this.openSettingsWindow());
    this.ipcMain.handle("desktop:open-main-window", () => this.restoreMainWindow());
  }

  registerLifecycleHandlers() {
    this.app.on("before-quit", () => {
      this.isQuitting = true;
    });
    this.app.on("activate", () => this.restoreMainWindow());
  }

  createTray() {
    this.tray = new this.Tray(createTrayImage(this.nativeImage));
    this.tray.setToolTip("MjolnirOS");
    this.tray.setContextMenu(
      this.Menu.buildFromTemplate([
        { label: "Open MjolnirOS", click: () => this.restoreMainWindow() },
        { label: "Settings", click: () => this.openSettingsWindow() },
        { type: "separator" },
        { label: "Restart", click: () => this.restart() },
        { label: "Quit MjolnirOS", click: () => this.quit() }
      ])
    );
    this.tray.on("click", () => this.restoreMainWindow());
  }

  createMainWindow() {
    this.mainWindow = new this.BrowserWindow({
      width: 1280,
      height: 820,
      minWidth: 960,
      minHeight: 640,
      show: false,
      backgroundColor: "#090f1a",
      title: "MjolnirOS",
      webPreferences: this.webPreferences()
    });
    this.mainWindow.once("ready-to-show", () => this.mainWindow.show());
    this.mainWindow.on("close", (event) => this.hideToTray(event));
    this.mainWindow.on("minimize", (event) => this.hideToTray(event));
    this.mainWindow.on("closed", () => {
      this.mainWindow = null;
    });
    this.loadWindowContent(this.mainWindow, "dashboard");
  }

  openSettingsWindow() {
    if (this.settingsWindow && !this.settingsWindow.isDestroyed()) {
      this.settingsWindow.show();
      this.settingsWindow.focus();
      return;
    }

    this.settingsWindow = new this.BrowserWindow({
      width: 620,
      height: 520,
      minWidth: 540,
      minHeight: 460,
      show: false,
      backgroundColor: "#090f1a",
      title: "MjolnirOS Settings",
      webPreferences: this.webPreferences()
    });
    this.settingsWindow.once("ready-to-show", () => this.settingsWindow.show());
    this.settingsWindow.on("closed", () => {
      this.settingsWindow = null;
    });
    this.loadWindowContent(this.settingsWindow, "settings");
  }

  restoreMainWindow() {
    if (!this.mainWindow || this.mainWindow.isDestroyed()) {
      this.createMainWindow();
      return;
    }
    if (this.mainWindow.isMinimized()) {
      this.mainWindow.restore();
    }
    this.mainWindow.show();
    this.mainWindow.focus();
    this.logger.info("main_window_restored");
  }

  hideToTray(event) {
    if (this.isQuitting) {
      return;
    }
    event.preventDefault();
    this.mainWindow.hide();
    this.logger.info("main_window_hidden_to_tray");
  }

  setLaunchOnStartup(enabled) {
    const launchOnStartup = enabled === true;
    this.applyLoginItemSetting(launchOnStartup);
    this.settings = this.settingsStore.save({ launchOnStartup });
    this.logger.info("windows_startup_preference_updated", { launchOnStartup });
    return this.settings;
  }

  applyLoginItemSetting(launchOnStartup) {
    const options = {
      openAtLogin: launchOnStartup,
      path: process.execPath,
      args: this.app.isPackaged ? [] : [this.app.getAppPath()]
    };
    this.app.setLoginItemSettings(options);
    this.logger.info("windows_login_item_updated", { launchOnStartup });
  }

  restart() {
    this.isQuitting = true;
    this.logger.info("desktop_runtime_restart_requested");
    this.app.relaunch();
    this.app.quit();
  }

  quit() {
    this.isQuitting = true;
    this.logger.info("desktop_runtime_quit_requested");
    this.app.quit();
  }

  webPreferences() {
    return {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false
    };
  }

  loadWindowContent(window, view) {
    if (this.app.isPackaged) {
      return window.loadFile(path.join(__dirname, "..", "frontend", "dist", "index.html"), {
        query: { view }
      });
    }

    const url = new URL(this.frontendUrl);
    url.searchParams.set("view", view);
    return window.loadURL(url.toString());
  }
}

module.exports = { DesktopRuntime, getSystemStatus };
