/* Run a Python command with the project virtualenv when present. */
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const candidates =
  process.platform === "win32"
    ? [
        resolve(root, ".venv/Scripts/python.exe"),
        resolve(root, ".venv/python.exe"),
        "python",
      ]
    : [resolve(root, ".venv/bin/python"), "python3"];
const python = candidates.find((candidate) =>
  candidate.includes(resolve(root)) ? existsSync(candidate) : true,
);

const result = spawnSync(python, process.argv.slice(2), {
  cwd: root,
  stdio: "inherit",
  env: { ...process.env, PYTHONUTF8: "1" },
});
process.exit(result.status ?? 1);
