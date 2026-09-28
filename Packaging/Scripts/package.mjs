#!/usr/bin/env node
/* Cross-platform packaging orchestrator for the Mosaic desktop application. */

import { execSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, readdirSync, realpathSync, statSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const codebaseDir = canonicalPath(resolve(__dirname, "../.."));
const packagingDir = resolve(__dirname, "..");
const tauriDir = join(codebaseDir, "Desktop/Tauri");
const releaseOutputDir = join(packagingDir, "release");
function canonicalPath(candidate) {
  const absolute = resolve(candidate);
  const suffix = [];
  let existing = absolute;
  while (!existsSync(existing)) {
    const parent = dirname(existing);
    if (parent === existing) return absolute;
    suffix.unshift(basename(existing));
    existing = parent;
  }
  return resolve(realpathSync.native(existing), ...suffix);
}

const privateDataRoot = canonicalPath(join(codebaseDir, "..", "Mosaic - Local Private Data"));

function assertNotPrivateDataPath(candidate, label) {
  const target = canonicalPath(candidate);
  if (target === privateDataRoot || target.startsWith(privateDataRoot + sep)) {
    throw new Error(label + " must never read or write the sibling private Data Root: " + target);
  }
  return target;
}

function assertInsideCodebase(candidate, label) {
  const target = assertNotPrivateDataPath(candidate, label);
  const pathFromCodebase = relative(codebaseDir, target);
  if (
    pathFromCodebase === ".." ||
    pathFromCodebase.startsWith(".." + sep) ||
    isAbsolute(pathFromCodebase)
  ) {
    throw new Error(label + " escapes the repository root: " + target);
  }
  return target;
}

function parseArgs() {
  const args = process.argv.slice(2);
  let target = "host";
  let release = false;
  let skipSidecar = false;
  let selfTestPathGuard = false;
  let checkPath = null;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--target" && args[i + 1]) {
      target = args[i + 1].toLowerCase();
      i++;
    } else if (args[i] === "--release") {
      release = true;
    } else if (args[i] === "--skip-sidecar") {
      skipSidecar = true;
    } else if (args[i] === "--self-test-path-guard") {
      selfTestPathGuard = true;
    } else if (args[i] === "--check-path" && args[i + 1]) {
      checkPath = args[i + 1];
      i++;
    }
  }
  return { target, release, skipSidecar, selfTestPathGuard, checkPath };
}

function getHostPlatform() {
  switch (process.platform) {
    case "win32":
      return "windows";
    case "darwin":
      return "macos";
    case "linux":
      return "linux";
    default:
      return process.platform;
  }
}

function sha256(path) {
  const content = readFileSync(path);
  return createHash("sha256").update(content).digest("hex");
}

function getGitSha() {
  try {
    return execSync("git rev-parse HEAD", { cwd: codebaseDir, encoding: "utf-8" }).trim();
  } catch {
    return "unknown";
  }
}

async function main() {
  const { target, release, skipSidecar, selfTestPathGuard, checkPath } = parseArgs();
  assertInsideCodebase(tauriDir, "Tauri build directory");
  assertInsideCodebase(releaseOutputDir, "release output directory");

  if (selfTestPathGuard) {
    let siblingRejected = false;
    try {
      assertNotPrivateDataPath(privateDataRoot, "path-guard self-test");
    } catch {
      siblingRejected = true;
    }
    if (!siblingRejected) {
      throw new Error("path-guard self-test did not reject the private sibling root");
    }
    console.log("PACKAGING PATH GUARD: PASS");
    return;
  }
  if (checkPath) {
    assertInsideCodebase(checkPath, "requested package path");
    console.log("PACKAGING PATH CHECK: PASS");
    return;
  }
  // Validate before any child build inherits CARGO_TARGET_DIR.  Otherwise a
  // hostile or stale environment could direct Cargo into the private sibling
  // before the later package-audit guard has a chance to reject it.
  const cargoTargetDir = assertNotPrivateDataPath(
    process.env.CARGO_TARGET_DIR || join(tauriDir, "target"),
    "Cargo target directory",
  );
  const host = getHostPlatform();

  console.log(`=== Mosaic Desktop Packaging Pipeline ===`);
  console.log(`Host Platform: ${host} (${process.arch})`);
  console.log(`Requested Target: ${target}`);

  if (target !== "host" && target !== host) {
    console.error(`\n[CROSS-COMPILATION NOTICE] Target '${target}' cannot be built on native '${host}'.`);
    console.error(`Desktop packaging for ${target} requires native ${target} build runners (or GitHub Actions CI).`);
    console.error(`See .github/workflows/build-and-package.yml for automated multi-platform matrix.\n`);
    process.exit(1);
  }

  // 1. Build Frontend Distribution
  console.log(`\n[1/5] Building Frontend bundle (tsc + vite build)...`);
  const buildFrontend = spawnSync("npm", ["--prefix", "App/Frontend", "run", "build"], {
    cwd: codebaseDir,
    stdio: "inherit",
    shell: process.platform === "win32",
  });
  if (buildFrontend.status !== 0) {
    console.error("Frontend build failed!");
    process.exit(buildFrontend.status ?? 1);
  }

  // 2. Build Python Backend Sidecar
  if (skipSidecar) {
    console.log(`\n[2/5] Skipping Python Backend Sidecar build (--skip-sidecar requested).`);
  } else {
    console.log(`\n[2/5] Packaging Python Backend Sidecar with PyInstaller...`);
    const pythonCmd = resolve(codebaseDir, "Scripts/run-py.mjs");
    const buildBackend = spawnSync(process.execPath, [pythonCmd, "Packaging/Scripts/build_backend.py"], {
      cwd: codebaseDir,
      stdio: "inherit",
    });
    if (buildBackend.status !== 0) {
      console.error("Backend sidecar build failed!");
      process.exit(buildBackend.status ?? 1);
    }
  }

  // 3. Build Tauri Desktop Package
  console.log(`\n[3/5] Building Native Tauri Desktop Package...`);
  const runTauriCmd = resolve(codebaseDir, "Scripts/run_tauri.mjs");
  const remap = `--remap-path-prefix=${homedir()}=/mosaic-build`;
  const tauriBuild = spawnSync(process.execPath, [runTauriCmd, "build"], {
    cwd: codebaseDir,
    stdio: "inherit",
    env: {
      ...process.env,
      CARGO_TARGET_DIR: cargoTargetDir,
      RUSTFLAGS: [process.env.RUSTFLAGS, remap].filter(Boolean).join(" "),
    },
  });
  if (tauriBuild.status !== 0) {
    console.error("Tauri build failed!");
    process.exit(tauriBuild.status ?? 1);
  }

  // 4. Scan and Audit Package Contents
  console.log(`\n[4/5] Running Package Content Security & Privacy Audit...`);
  const bundleBase = assertNotPrivateDataPath(join(cargoTargetDir, "release", "bundle"), "bundle directory");
  if (!existsSync(bundleBase)) {
    console.error(`Bundle directory not found at: ${bundleBase}`);
    process.exit(1);
  }

  const auditCmd = resolve(codebaseDir, "Scripts/run-py.mjs");
  const nativeBinary = assertNotPrivateDataPath(
    join(cargoTargetDir, "release", `people-relationships${host === "windows" ? ".exe" : ""}`),
    "native binary",
  );
  const auditResult = spawnSync(process.execPath, [auditCmd, "Packaging/Scripts/audit_package.py", bundleBase, nativeBinary], {
    cwd: codebaseDir,
    stdio: "inherit",
  });
  if (auditResult.status !== 0) {
    console.error("Package privacy audit failed!");
    process.exit(auditResult.status ?? 1);
  }

  // 5. Generate Release Manifest and Collect Artifacts
  console.log(`\n[5/5] Generating Release Manifest...`);
  mkdirSync(releaseOutputDir, { recursive: true });

  const collectedArtifacts = [];
  function scanDir(dir) {
    if (!existsSync(dir)) return;
    const entries = readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = join(dir, entry.name);
      if (entry.isDirectory()) {
        scanDir(fullPath);
      } else if (entry.isFile()) {
        const ext = entry.name.toLowerCase();
        if (
          ext.endsWith(".exe") ||
          ext.endsWith(".msi") ||
          ext.endsWith(".dmg") ||
          ext.endsWith(".appimage") ||
          ext.endsWith(".deb")
        ) {
          const stats = statSync(fullPath);
          collectedArtifacts.push({
            name: entry.name,
            // A release manifest can be shared with a public build.  Keep its
            // artifact references portable and do not leak a builder's local
            // filesystem layout.
            path: relative(bundleBase, fullPath).replaceAll("\\", "/"),
            size_bytes: stats.size,
            size_mb: (stats.size / (1024 * 1024)).toFixed(2),
            sha256: sha256(fullPath),
          });
        }
      }
    }
  }

  scanDir(bundleBase);

  // Find sidecar binary hash
  const sidecarsDir = join(tauriDir, "binaries");
  let sidecarInfo = null;
  if (existsSync(sidecarsDir)) {
    const sidecarFiles = readdirSync(sidecarsDir);
    for (const f of sidecarFiles) {
      if (f.startsWith("people-relationships-backend")) {
        const p = join(sidecarsDir, f);
        sidecarInfo = {
          name: f,
          sha256: sha256(p),
          size_bytes: statSync(p).size,
        };
        break;
      }
    }
  }

  let appVersion = "0.5.0";
  try {
    const pkg = JSON.parse(readFileSync(join(codebaseDir, "package.json"), "utf-8"));
    if (pkg.version) appVersion = pkg.version;
  } catch {}

  const manifest = {
    app_name: "Mosaic",
    version: appVersion,
    git_sha: getGitSha(),
    target_os: host,
    target_arch: process.arch,
    build_timestamp: new Date().toISOString(),
    backend_sidecar: sidecarInfo,
    artifacts: collectedArtifacts,
    privacy_audit: {
      status: "PASS",
      verified_zero_private_data: true,
      verified_by: "Packaging/Scripts/audit_package.py",
    },
  };

  const manifestPath = join(releaseOutputDir, `release-manifest-${host}-${process.arch}.json`);
  writeFileSync(manifestPath, JSON.stringify(manifest, null, 2), "utf-8");

  console.log(`\n======================================================`);
  console.log(`🎉 PACKAGING COMPLETE!`);
  console.log(`Release Manifest: ${manifestPath}`);
  console.log(`Artifacts (${collectedArtifacts.length}):`);
  for (const art of collectedArtifacts) {
    console.log(`  - ${art.name} (${art.size_mb} MB) [SHA: ${art.sha256}]`);
  }
  console.log(`======================================================\n`);
}

main().catch((err) => {
  console.error("Packaging script error:", err);
  process.exit(1);
});
