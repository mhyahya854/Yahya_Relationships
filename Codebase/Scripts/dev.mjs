/* Launch the FastAPI backend and the Vite frontend together.
   Ctrl+C stops both. */
import { spawn } from "node:child_process";
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

const backend = spawn(python, ["-m", "app.backend.main"], {
  cwd: root,
  stdio: "inherit",
  env: { ...process.env, PYTHONUTF8: "1" },
});

const vite = spawn(
  process.platform === "win32" ? "npm.cmd" : "npm",
  ["--prefix", "App/Frontend", "run", "dev"],
  {
  cwd: root,
  stdio: "inherit",
  },
);

function shutdown(signal) {
  if (!backend.killed) backend.kill(signal);
  if (!vite.killed) vite.kill(signal);
  setTimeout(() => process.exit(0), 800);
}

process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));

backend.on("error", (error) => console.error("backend error:", error));
vite.on("error", (error) => console.error("vite error:", error));
