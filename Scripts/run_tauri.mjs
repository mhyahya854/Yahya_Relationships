/* Cross-platform runner for Tauri CLI commands from Desktop/Tauri directory. */
import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const root = resolve(__dirname, "..");
const tauriDir = resolve(root, "Desktop/Tauri");

const result = spawnSync("npx", ["tauri", ...process.argv.slice(2)], {
  cwd: tauriDir,
  stdio: "inherit",
  shell: process.platform === "win32",
});
process.exit(result.status ?? 1);
