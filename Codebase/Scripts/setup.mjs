/* Setup script for Family Relationships developer environment.
   Sets up Python virtualenv with editable package install and installs npm dependencies. */
import { execSync, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const venvPython = process.platform === "win32"
  ? resolve(root, ".venv/Scripts/python.exe")
  : resolve(root, ".venv/bin/python");

console.log("=== Setting up People Relationships environment ===");

// 1. Python virtualenv
if (!existsSync(venvPython)) {
  console.log("Creating virtual environment at Codebase/.venv ...");
  const sysPython = process.platform === "win32" ? "python" : "python3";
  execSync(`${sysPython} -m venv .venv`, { cwd: root, stdio: "inherit" });
}

// 2. Install backend package in editable mode
console.log("Installing backend package (editable mode) and dependencies ...");
execSync(`"${venvPython}" -m pip install --upgrade pip`, { cwd: root, stdio: "inherit" });
execSync(`"${venvPython}" -m pip install -e App`, { cwd: root, stdio: "inherit" });

// 3. Frontend npm dependencies
console.log("Installing frontend dependencies ...");
execSync("npm --prefix App/Frontend install", { cwd: root, stdio: "inherit" });

console.log("=== Setup complete! Run 'npm run dev' to start the application. ===");
