/* Launch the FastAPI backend and the Vite frontend together.
   Ctrl+C stops both. */
import { spawn, execSync } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const python =
  process.platform === "win32"
    ? existsSync(resolve(root, ".venv/Scripts/python.exe"))
      ? resolve(root, ".venv/Scripts/python.exe")
      : "python"
    : existsSync(resolve(root, ".venv/bin/python"))
      ? resolve(root, ".venv/bin/python")
      : "python3";

const appDir = resolve(root, "App");
const scriptsDir = resolve(root, "Scripts");
const existingPythonPath = process.env.PYTHONPATH || "";
const pythonPathParts = [appDir, scriptsDir, root];
if (existingPythonPath) pythonPathParts.push(existingPythonPath);
const pythonPath = pythonPathParts.join(process.platform === "win32" ? ";" : ":");

const backend = spawn(python, ["-m", "app.backend.main"], {
  cwd: root,
  stdio: "inherit",
  env: { ...process.env, PYTHONUTF8: "1", PYTHONPATH: pythonPath },
});

const vite = spawn(
  process.platform === "win32" ? "npm.cmd" : "npm",
  ["--prefix", "App/Frontend", "run", "dev"],
  {
  cwd: root,
  stdio: "inherit",
  // Windows: .cmd shims require a shell on modern Node (CVE-2024-27980).
  shell: process.platform === "win32",
  },
);

function shutdown(signal) {
  if (process.platform === "win32") {
    if (backend.pid) {
      try { execSync(`taskkill /PID ${backend.pid} /T /F`, { stdio: "ignore" }); } catch {}
    }
    if (vite.pid) {
      try { execSync(`taskkill /PID ${vite.pid} /T /F`, { stdio: "ignore" }); } catch {}
    }
  } else {
    if (!backend.killed) backend.kill(signal);
    if (!vite.killed) vite.kill(signal);
  }
  setTimeout(() => process.exit(0), 400);
}

process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));

backend.on("error", (error) => console.error("backend error:", error));
vite.on("error", (error) => console.error("vite error:", error));
