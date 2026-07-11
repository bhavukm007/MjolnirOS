"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const assert = require("node:assert/strict");

const { DesktopSettingsStore } = require("./desktop_settings");
const { DesktopRuntime, getSystemStatus } = require("./runtime");

const logger = {
  info() {},
  warning() {},
  error() {}
};

test("desktop settings default to startup disabled and persist user changes", () => {
  const temporaryDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "mjolniros-settings-"));
  const settingsPath = path.join(temporaryDirectory, "desktop-settings.json");
  const settingsStore = new DesktopSettingsStore(settingsPath, logger);

  try {
    assert.deepEqual(settingsStore.load(), { launchOnStartup: false });
    assert.deepEqual(settingsStore.save({ launchOnStartup: true }), { launchOnStartup: true });
    assert.deepEqual(settingsStore.load(), { launchOnStartup: true });
  } finally {
    fs.rmSync(temporaryDirectory, { recursive: true, force: true });
  }
});

test("desktop runtime applies startup registration when the preference changes", () => {
  const loginItemCalls = [];
  const settingsStore = {
    save: (settings) => settings
  };
  const runtime = new DesktopRuntime({
    app: {
      isPackaged: false,
      getAppPath: () => "D:/Programs/MjolnirOS",
      setLoginItemSettings: (options) => loginItemCalls.push(options)
    },
    BrowserWindow: class {},
    Tray: class {},
    Menu: {},
    nativeImage: {},
    ipcMain: {},
    settingsStore,
    logger,
    frontendUrl: "http://127.0.0.1:5173"
  });

  const enabledSettings = runtime.setLaunchOnStartup(true);
  const disabledSettings = runtime.setLaunchOnStartup(false);

  assert.deepEqual(enabledSettings, { launchOnStartup: true });
  assert.deepEqual(disabledSettings, { launchOnStartup: false });
  assert.equal(loginItemCalls.length, 2);
  assert.equal(loginItemCalls[0].openAtLogin, true);
  assert.equal(loginItemCalls[1].openAtLogin, false);
  assert.deepEqual(loginItemCalls[0].args, ["D:/Programs/MjolnirOS"]);
});

test("system status returns usable dashboard metrics", () => {
  const systemStatus = getSystemStatus();

  assert.ok(systemStatus.cpuCount > 0);
  assert.ok(systemStatus.memoryTotalBytes > 0);
  assert.ok(systemStatus.memoryUsedBytes >= 0);
  assert.equal(systemStatus.runningAgents, 0);
});

test("tray exposes required actions and restores the hidden dashboard", () => {
  const menuTemplate = [];
  const trayHandlers = {};
  const mainWindow = {
    isDestroyed: () => false,
    isMinimized: () => true,
    restore: () => mainWindow.restored = true,
    show: () => mainWindow.shown = true,
    focus: () => mainWindow.focused = true
  };
  const runtime = new DesktopRuntime({
    app: { isPackaged: false, getAppPath: () => "D:/Programs/MjolnirOS" },
    BrowserWindow: class {},
    Tray: class {
      setToolTip() {}
      setContextMenu(menu) {
        this.menu = menu;
      }
      on(event, handler) {
        trayHandlers[event] = handler;
      }
    },
    Menu: {
      buildFromTemplate: (template) => {
        menuTemplate.push(...template);
        return template;
      }
    },
    nativeImage: { createFromDataURL: () => ({}) },
    ipcMain: {},
    settingsStore: {},
    logger,
    frontendUrl: "http://127.0.0.1:5173"
  });
  runtime.mainWindow = mainWindow;

  runtime.createTray();
  trayHandlers.click();

  assert.deepEqual(menuTemplate.filter((item) => item.label).map((item) => item.label), [
    "Open MjolnirOS",
    "Settings",
    "Restart",
    "Quit MjolnirOS"
  ]);
  assert.equal(mainWindow.restored, true);
  assert.equal(mainWindow.shown, true);
  assert.equal(mainWindow.focused, true);
});

test("closing the dashboard hides it to the tray until the app quits", () => {
  const event = { preventDefault: () => event.prevented = true };
  const runtime = new DesktopRuntime({
    app: {},
    BrowserWindow: class {},
    Tray: class {},
    Menu: {},
    nativeImage: {},
    ipcMain: {},
    settingsStore: {},
    logger,
    frontendUrl: "http://127.0.0.1:5173"
  });
  runtime.mainWindow = { hide: () => runtime.mainWindow.hidden = true };

  runtime.hideToTray(event);

  assert.equal(event.prevented, true);
  assert.equal(runtime.mainWindow.hidden, true);
});
