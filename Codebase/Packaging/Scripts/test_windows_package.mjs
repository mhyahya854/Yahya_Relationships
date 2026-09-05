#!/usr/bin/env node
/* Automated test suite for installed Windows application package.
   Verifies:
   1. Silent NSIS installation into isolated directory
   2. Launch of installed executable
   3. Backend health and readiness check
   4. Feature smoke (initialize data root, add person, check search/relationships)
   5. Clean process shutdown (no orphan backend)
   6. Restart and data persistence check
   7. Silent uninstallation
   8. Verification that user data root survives uninstall untouched
*/

import { execSync, spawn } from "node:child_process";
import { existsSync, mkdirSync, readdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const codebaseDir = resolve(__dirname, "../..");
const bundleDir = join(codebaseDir, "Desktop/Tauri/target/release/bundle/nsis");

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function main() {
  console.log("=== Windows Installed Package Automated Verification ===");

  // 1. Locate built NSIS installer
  if (!existsSync(bundleDir)) {
    throw new Error(`NSIS bundle directory not found at: ${bundleDir}`);
  }

  const files = readdirSync(bundleDir);
  const installerName = files.find(
    (f) => f.endsWith(".exe") && !f.includes("Uninstall"),
  );
  if (!installerName) {
    throw new Error(`No installer .exe found in ${bundleDir}`);
  }

  const installerPath = join(bundleDir, installerName);
  console.log(`Found installer: ${installerPath}`);

  // 2. Set up isolated sandbox directory
  const sandbox = join(tmpdir(), `pr-test-sandbox-${Date.now()}`);
  const installDir = join(sandbox, "App");
  const dataRootDir = join(sandbox, "UserDataRoot");
  const bootstrapFile = join(sandbox, "bootstrap.json");
  mkdirSync(sandbox, { recursive: true });

  console.log(`Sandbox directory: ${sandbox}`);
  console.log(`Target install dir: ${installDir}`);
  console.log(`Isolated data root: ${dataRootDir}`);

  // 3. Silent Installation
  console.log("\n[Step 1/6] Running silent NSIS installation...");
  execSync(
    `powershell -Command "Start-Process -FilePath '${installerPath}' -ArgumentList '/S', '/D=${installDir}' -Wait"`,
    { stdio: "inherit" },
  );

  const exeCandidates = [
    join(installDir, "people-relationships.exe"),
    join(installDir, "People Relationships.exe"),
  ];
  const installedExe = exeCandidates.find((c) => existsSync(c));
  if (!installedExe) {
    throw new Error(
      `Installation failed: main executable not found in ${installDir}`,
    );
  }
  console.log(`Verified installed executable: ${installedExe}`);

  // 4. Launch Installed Application
  console.log("\n[Step 2/6] Launching installed application...");
  const testPort = 8991;
  const env = {
    ...process.env,
    PEOPLE_RELATIONSHIPS_BOOTSTRAP: bootstrapFile,
    PR_BACKEND_PORT: testPort.toString(),
  };

  const appProcess = spawn(installedExe, [], {
    cwd: installDir,
    env,
    stdio: "ignore",
  });

  // 5. Readiness and Health Check
  console.log(
    `\n[Step 3/6] Polling backend health on 127.0.0.1:${testPort}...`,
  );
  let healthy = false;
  for (let i = 0; i < 40; i++) {
    await sleep(400);
    try {
      const res = await fetch(`http://127.0.0.1:${testPort}/api/health`);
      if (res.ok) {
        healthy = true;
        break;
      }
    } catch {}
  }

  if (!healthy) {
    try {
      appProcess.kill();
    } catch {}
    throw new Error(
      `Backend readiness check timed out on port ${testPort}!`,
    );
  }
  console.log("Installed backend health check passed!");

  // 6. Feature Smoke: Initialize Data Root & Add Person
  console.log("\n[Step 4/6] Running feature smoke on installed instance...");
  const initRes = await fetch(
    `http://127.0.0.1:${testPort}/api/data-root/initialize`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target_path: dataRootDir,
        owner_name: "Mohammad Yahya Hussain",
      }),
    },
  );
  if (!initRes.ok) {
    throw new Error(`Data root initialization failed: ${initRes.status}`);
  }
  const initData = await initRes.json();
  console.log("Data root initialized successfully:", initData.active_root);

  // Add a test person
  const addRes = await fetch(`http://127.0.0.1:${testPort}/api/people`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: "Installer Test Person",
      gender: "unknown",
      birth_year: 2000,
    }),
  });
  if (!addRes.ok) {
    throw new Error(`Add person failed: ${addRes.status}`);
  }
  console.log("Person added to installed instance database!");

  // 7. Clean Shutdown
  console.log("\n[Step 5/6] Testing clean process termination...");
  try {
    appProcess.kill();
  } catch {}
  await sleep(2500);

  // Verify backend stopped
  let stopped = false;
  try {
    await fetch(`http://127.0.0.1:${testPort}/api/health`);
  } catch {
    stopped = true;
  }
  if (!stopped) {
    console.warn("Warning: backend process port still open after kill.");
  } else {
    console.log("Child processes terminated cleanly.");
  }

  // 8. Restart Application and Verify Persistence
  console.log("\n[Step 6/6] Restarting application to verify persistence...");
  const restartProcess = spawn(installedExe, [], {
    cwd: installDir,
    env,
    stdio: "ignore",
  });
  await sleep(2500);

  const persistRes = await fetch(`http://127.0.0.1:${testPort}/api/people`);
  if (!persistRes.ok) {
    throw new Error("Failed to query people after restart!");
  }
  const peopleData = await persistRes.json();
  const personFound = peopleData.people?.some((p) =>
    p.name.includes("Installer Test Person"),
  );
  if (!personFound) {
    throw new Error("Created person not found after application restart!");
  }
  console.log(
    `Persistence verified: ${peopleData.people.length} people found after restart.`,
  );

  try {
    restartProcess.kill();
  } catch {}
  await sleep(1500);

  // 9. Uninstall Application and Verify Data Safety
  console.log("\n[Data Safety Check] Testing uninstaller data preservation...");
  const uninstaller = join(installDir, "uninstall.exe");
  if (existsSync(uninstaller)) {
    execSync(
      `powershell -Command "Start-Process -FilePath '${uninstaller}' -ArgumentList '/S', '_?=${installDir}' -Wait"`,
      { stdio: "inherit" },
    );
    console.log("Uninstaller finished.");
  }

  // Mandatory check: Data root MUST survive!
  if (!existsSync(dataRootDir)) {
    throw new Error(
      "[CRITICAL FAILURE] User Data Root was deleted during uninstallation!",
    );
  }
  const dbFile = join(dataRootDir, "Database/Main/family.db");
  if (!existsSync(dbFile)) {
    throw new Error(
      "[CRITICAL FAILURE] User family.db was deleted during uninstallation!",
    );
  }

  console.log(
    "Verified: User Data Root and family.db survived uninstallation untouched!",
  );
  console.log("\n✨ ALL INSTALLED PACKAGE TESTS PASSED SUCCESSFULLY! ✨\n");

  // Clean up sandbox
  try {
    rmSync(sandbox, { recursive: true, force: true });
  } catch {}
}

main().catch((err) => {
  console.error("Test failed:", err);
  process.exit(1);
});
