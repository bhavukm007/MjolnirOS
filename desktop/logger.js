"use strict";

const fs = require("node:fs");
const path = require("node:path");

class DesktopLogger {
  constructor(logFilePath) {
    this.logFilePath = logFilePath;
  }

  info(event, context = {}) {
    this.write("INFO", event, context);
  }

  warning(event, context = {}) {
    this.write("WARNING", event, context);
  }

  error(event, context = {}) {
    this.write("ERROR", event, context);
  }

  write(level, event, context) {
    const entry = JSON.stringify({
      timestamp: new Date().toISOString(),
      level,
      logger: "desktop",
      event,
      ...context
    });

    try {
      fs.mkdirSync(path.dirname(this.logFilePath), { recursive: true });
      fs.appendFileSync(this.logFilePath, `${entry}\n`, "utf8");
      process.stdout.write(`${entry}\n`);
    } catch (error) {
      process.stderr.write(`Unable to write desktop log: ${error.message}\n`);
    }
  }
}

module.exports = { DesktopLogger };
