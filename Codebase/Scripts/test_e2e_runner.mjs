import { spawn, spawnSync, execSync } from "node:child_process";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");

console.log("=== Starting Dev Stack for E2E Testing ===");
const devProcess = spawn(process.execPath, [resolve(root, "Scripts/dev.mjs")], {
  cwd: root,
  stdio: "inherit",
});

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
  if (process.platform === "win32") {
    try {
      execSync(`taskkill /PID ${devProcess.pid} /T /F`, { stdio: "ignore" });
    } catch {}
  } else {
    devProcess.kill("SIGINT");
  }
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);

async function run() {
  try {
    console.log("Waiting for backend (http://127.0.0.1:8765/api/health)...");
    const backendReady = await waitForUrl("http://127.0.0.1:8765/api/health", 20000);
    if (!backendReady) {
      throw new Error("Backend did not become healthy within timeout.");
    }
    console.log("Backend is ready!");

    console.log("Waiting for frontend (http://localhost:1420)...");
    const frontendReady = await waitForUrl("http://localhost:1420", 25000);
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
      cwd: resolve(root, ".."),
      stdio: "inherit",
    });
    setTimeout(() => process.exit(process.exitCode ?? 0), 500);
  }
}

void run();
