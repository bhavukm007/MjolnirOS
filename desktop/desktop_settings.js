"use strict";

const fs = require("node:fs");
const path = require("node:path");

const DEFAULT_DESKTOP_SETTINGS = Object.freeze({
  launchOnStartup: false
});

class DesktopSettingsStore {
  constructor(filePath, logger) {
    this.filePath = filePath;
    this.logger = logger;
  }

  load() {
    if (!fs.existsSync(this.filePath)) {
      this.save(DEFAULT_DESKTOP_SETTINGS);
      return { ...DEFAULT_DESKTOP_SETTINGS };
    }

    const serializedSettings = fs.readFileSync(this.filePath, "utf8");
    const parsedSettings = JSON.parse(serializedSettings);
    return this.normalize(parsedSettings);
  }

  save(settings) {
    const normalizedSettings = this.normalize(settings);
    fs.mkdirSync(path.dirname(this.filePath), { recursive: true });
    fs.writeFileSync(this.filePath, `${JSON.stringify(normalizedSettings, null, 2)}\n`, "utf8");
    this.logger.info("desktop_settings_saved", normalizedSettings);
    return normalizedSettings;
  }

  normalize(settings) {
    return {
      launchOnStartup: settings?.launchOnStartup === true
    };
  }
}

module.exports = { DEFAULT_DESKTOP_SETTINGS, DesktopSettingsStore };
