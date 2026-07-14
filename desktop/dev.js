const { spawn } = require("node:child_process");
const http = require("node:http");
const path = require("node:path");

const projectRoot = path.join(__dirname, "..");
const vite = path.join(projectRoot, "frontend", "node_modules", "vite", "bin", "vite.js");
const electron = require("electron");
const frontendUrl = process.env.MJOLNIROS_FRONTEND_URL || "http://127.0.0.1:5173";
const parsedFrontendUrl = new URL(frontendUrl);
let frontendProcess;
let electronProcess;
let stopping = false;

function frontendIsReady() {
  return new Promise((resolve) => {
    const request = http.get(frontendUrl, (response) => {
      response.resume();
      resolve(response.statusCode === 200);
    });
    request.setTimeout(1000, () => request.destroy());
    request.on("error", () => resolve(false));
  });
}

function pause(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function waitForFrontend() {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    if (await frontendIsReady()) return;
    if (frontendProcess.exitCode !== null) {
      throw new Error(`Vite exited with code ${frontendProcess.exitCode}.`);
    }
    await pause(250);
  }
  throw new Error("Vite did not become ready on port 5173.");
}

function stop(exitCode = 0) {
  if (stopping) return;
  stopping = true;
  if (electronProcess && electronProcess.exitCode === null) electronProcess.kill();
  if (frontendProcess && frontendProcess.exitCode === null) frontendProcess.kill();
  process.exitCode = exitCode;
}

async function start() {
  frontendProcess = spawn(
    process.execPath,
    [vite, "--host", parsedFrontendUrl.hostname, "--port", parsedFrontendUrl.port || "5173"],
    {
    cwd: path.join(projectRoot, "frontend"),
    stdio: "inherit",
    windowsHide: true,
    }
  );
  await waitForFrontend();
  electronProcess = spawn(electron, [projectRoot, ...process.argv.slice(2)], {
    cwd: projectRoot,
    stdio: "inherit",
  });
  electronProcess.on("exit", (code) => stop(code ?? 1));
}

process.on("SIGINT", () => stop(0));
process.on("SIGTERM", () => stop(0));
process.on("exit", () => {
  if (electronProcess && electronProcess.exitCode === null) electronProcess.kill();
  if (frontendProcess && frontendProcess.exitCode === null) frontendProcess.kill();
});

start().catch((error) => {
  console.error(`[dev] ${error.message}`);
  stop(1);
});
