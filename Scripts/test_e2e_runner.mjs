import { spawn, spawnSync, execFileSync } from "node:child_process";
import { createServer } from "node:net";
import { resolve } from "node:path";
import { mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";

const root = resolve(import.meta.dirname, "..");
const tempRoot = resolve(tmpdir(), `smoke_e2e_root_${Date.now()}`);
mkdirSync(tempRoot, { recursive: true });
const pythonExe = process.platform === "win32"
  ? resolve(root, ".venv/Scripts/python.exe")
  : resolve(root, ".venv/bin/python");
const fixtureEnvironment = {
  ...process.env,
  PYTHONUTF8: "1",
  MOSAIC_ISOLATED_TEST_ROOT: "1",
  PYTHONPATH: [resolve(root, "App"), resolve(root, "Scripts"), root, process.env.PYTHONPATH]
    .filter(Boolean).join(process.platform === "win32" ? ";" : ":"),
};
const seeded = spawnSync(pythonExe, [
  "-c",
  "from pathlib import Path; from Tests.synthetic_mosaic import build; import sys; build(Path(sys.argv[1]), include_backup=True)",
  tempRoot,
], { cwd: root, env: fixtureEnvironment, stdio: "inherit" });
if (seeded.status !== 0) {
  throw new Error("Could not build an isolated synthetic E2E Data Root.");
}

console.log(`=== Setting up Isolated Data Root at ${tempRoot} ===`);
console.log("=== Starting Dev Stack for E2E Testing ===");
let devProcess = null;

async function freePort() {
  return new Promise((resolvePort, rejectPort) => {
    const server = createServer();
    server.once("error", rejectPort);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      server.close((error) => error ? rejectPort(error) : resolvePort(address.port));
    });
  });
}

async function waitForUrl(url, timeoutMs = 25000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(url);
      if (res.ok) return true;
    } catch {}
    await new Promise((r) => setTimeout(r, 800));
  }
  return false;
}

function shutdown() {
  console.log("Shutting down dev process...");
  try {
    if (devProcess && !devProcess.killed && devProcess.pid) {
      if (process.platform === "win32") {
        execFileSync("taskkill", ["/pid", String(devProcess.pid), "/T", "/F"], { stdio: "ignore" });
      } else {
        devProcess.kill("SIGINT");
      }
    }
  } catch {}
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);

async function run() {
  try {
    const backendPort = await freePort();
    const frontendPort = await freePort();
    const apiOrigin = `http://127.0.0.1:${backendPort}`;
    const webOrigin = `http://localhost:${frontendPort}`;
    devProcess = spawn(process.execPath, [resolve(root, "Scripts/dev.mjs")], {
      cwd: root,
      stdio: "inherit",
      env: {
        ...fixtureEnvironment,
        PEOPLE_RELATIONSHIPS_ROOT: tempRoot,
        PR_BACKEND_PORT: String(backendPort),
        PR_FRONTEND_PORT: String(frontendPort),
        VITE_BACKEND_URL: apiOrigin,
      },
    });

    console.log(`Waiting for backend (${apiOrigin}/api/health)...`);
    const backendReady = await waitForUrl(`${apiOrigin}/api/health`, 20000);
    if (!backendReady) {
      throw new Error("Backend did not become healthy within timeout.");
    }
    console.log("Backend is ready!");

    console.log(`Waiting for frontend (${webOrigin})...`);
    const frontendReady = await waitForUrl(webOrigin, 25000);
    if (!frontendReady) {
      throw new Error("Frontend did not become ready within timeout.");
    }
    console.log("Frontend is ready!");

    console.log("=== Running UI Smoke Tests (smoke.mjs) ===");
    const smokeResult = spawnSync(process.execPath, [resolve(root, "Tests/UI/smoke.mjs")], {
      cwd: resolve(root, "Tests/UI"),
      stdio: "inherit",
    });

    if (smokeResult.status !== 0) {
      throw new Error(`smoke.mjs exited with code ${smokeResult.status}`);
    }

    console.log("=== UI / E2E Testing SUCCESS! ===");
  } catch (err) {
    console.error("E2E Test Failed:", err);
    process.exitCode = 1;
  } finally {
    shutdown();
    await new Promise((r) => setTimeout(r, 1000));
    console.log("=== Cleaning Smoke Test Data ===");
    const pythonExe = process.platform === "win32"
      ? resolve(root, ".venv/Scripts/python.exe")
      : resolve(root, ".venv/bin/python");
    spawnSync(pythonExe, [resolve(root, "Tests/UI/clean_smoke_data.py")], {
      cwd: root,
      stdio: "inherit",
      env: {
        ...fixtureEnvironment,
        PEOPLE_RELATIONSHIPS_ROOT: tempRoot,
      },
    });
    try {
      rmSync(tempRoot, { recursive: true, force: true });
    } catch {}
    setTimeout(() => process.exit(process.exitCode ?? 0), 500);
  }
}

void run();
