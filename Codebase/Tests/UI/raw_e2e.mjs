import puppeteer from "puppeteer-core";
import { createHash } from "node:crypto";
import { execFileSync, spawn } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "../..");
const REPO = resolve(ROOT, "..");
const SHOTS = resolve(REPO, "Documentation/UI-Screenshots/Phase12-Raw");
const EDGE = existsSync("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
  ? "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
  : "C:/Program Files/Microsoft/Edge/Application/msedge.exe";
const python = resolve(ROOT, ".venv/Scripts/python.exe");
const sandbox = resolve(tmpdir(), `mosaic_phase12_raw_e2e_${Date.now()}`);
const bootstrap = join(sandbox, "settings", "bootstrap.json");
const syntheticRoot = join(sandbox, "Raw UI Evidence Root");
const realBootstrap = join(process.env.APPDATA ?? "", "people-relationships", "bootstrap.json");

function sha256(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function inventory(root) {
  if (!existsSync(root)) return [];
  const files = [];
  function scan(directory) {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) scan(path);
      else if (entry.isFile()) files.push({ path: relative(root, path).replaceAll("\\", "/"), bytes: statSync(path).size, sha256: sha256(path) });
    }
  }
  scan(root);
  return files.sort((a, b) => a.path.localeCompare(b.path));
}

const productionBefore = {
  database: inventory(resolve(REPO, "Database")),
  people: inventory(resolve(REPO, "People")),
  backups: inventory(resolve(REPO, "Backups")),
  raw: inventory(resolve(REPO, "Raw")),
  bootstrap: existsSync(realBootstrap) ? { bytes: statSync(realBootstrap).size, sha256: sha256(realBootstrap) } : null,
};

function assertProductionUntouched() {
  const after = {
    database: inventory(resolve(REPO, "Database")),
    people: inventory(resolve(REPO, "People")),
    backups: inventory(resolve(REPO, "Backups")),
    raw: inventory(resolve(REPO, "Raw")),
    bootstrap: existsSync(realBootstrap) ? { bytes: statSync(realBootstrap).size, sha256: sha256(realBootstrap) } : null,
  };
  if (JSON.stringify(after) !== JSON.stringify(productionBefore)) throw new Error("Phase 12 UI E2E changed production data.");
}

const sleep = (milliseconds) => new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds));
async function waitForUrl(url, timeout = 30_000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    try { const response = await fetch(url); if (response.ok) return; } catch {}
    await sleep(250);
  }
  throw new Error(`Timed out waiting for ${url}`);
}
async function request(path, init) {
  const response = await fetch(`http://127.0.0.1:8765${path}`, init);
  const payload = await response.json();
  if (!response.ok) throw new Error(`${path}: ${JSON.stringify(payload)}`);
  return payload;
}
async function post(path, body) {
  return request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}
function stop(child) {
  if (!child?.pid) return;
  try { execFileSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" }); } catch {}
}

let browser;
let page;
let backend;
let vite;
let steps = 0;
const consoleErrors = [];
function step(message) { steps += 1; console.log(`✓ [Raw E2E ${steps}] ${message}`); }

async function clickText(scope, text) {
  await page.waitForFunction((selector, expected) => [...document.querySelectorAll(`${selector} button`)].some((button) => {
    const box = button.getBoundingClientRect();
    return button.textContent?.includes(expected) && !button.disabled && box.width > 0 && box.height > 0;
  }), { timeout: 20_000 }, scope, text);
  await page.evaluate((selector, expected) => [...document.querySelectorAll(`${selector} button`)].find((button) => {
    const box = button.getBoundingClientRect();
    return button.textContent?.includes(expected) && !button.disabled && box.width > 0 && box.height > 0;
  })?.click(), scope, text);
}

async function setValue(selector, value) {
  await page.waitForSelector(selector, { visible: true, timeout: 20_000 });
  await page.$eval(selector, (element, next) => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(element, next);
    element.dispatchEvent(new Event("input", { bubbles: true }));
  }, value);
}

async function selectRaw(pathText) {
  await page.waitForFunction((expected) => [...document.querySelectorAll(".raw-table tbody tr")]
    .some((row) => row.textContent?.includes(expected)), { timeout: 20_000 }, pathText);
  await page.evaluate((expected) => [...document.querySelectorAll(".raw-table tbody tr")]
    .find((row) => row.textContent?.includes(expected))?.click(), pathText);
  await page.waitForFunction((expected) => document.querySelector(".raw-detail")?.textContent?.includes(expected), { timeout: 20_000 }, pathText);
}

async function screenshot(name) {
  await sleep(250);
  writeFileSync(join(SHOTS, name), await page.screenshot({ fullPage: true }));
}

try {
  if (!existsSync(python)) throw new Error(`Expected test virtualenv at ${python}`);
  if (!existsSync(EDGE)) throw new Error("Microsoft Edge is required for the Raw UI E2E.");
  mkdirSync(dirname(bootstrap), { recursive: true });
  mkdirSync(SHOTS, { recursive: true });
  const env = { ...process.env, PYTHONUTF8: "1", PEOPLE_RELATIONSHIPS_BOOTSTRAP: bootstrap };
  delete env.PEOPLE_RELATIONSHIPS_ROOT;
  env.PYTHONPATH = [resolve(ROOT, "App"), resolve(ROOT, "Scripts"), ROOT, env.PYTHONPATH].filter(Boolean).join(";");
  backend = spawn(python, ["-m", "app.backend.main"], { cwd: ROOT, env, stdio: "pipe" });
  vite = spawn("npm.cmd", ["--prefix", "App/Frontend", "run", "dev", "--", "--strictPort"], { cwd: ROOT, env, stdio: "pipe", shell: true });
  backend.stderr.on("data", (data) => { if (/Traceback|ERROR/.test(data.toString())) console.error(data.toString()); });
  vite.stderr.on("data", (data) => console.error(data.toString()));
  await waitForUrl("http://127.0.0.1:8765/api/health");
  await waitForUrl("http://localhost:1420");

  await post("/api/data-root/initialize", { target_path: syntheticRoot, owner_name: "Raw UI Owner", owner_gender: "unknown" });
  browser = await puppeteer.launch({ executablePath: EDGE, headless: "new", args: ["--disable-gpu", "--no-first-run", "--no-sandbox", "--edge-skip-compat-layer-relaunch"], defaultViewport: { width: 1500, height: 1000 } });
  page = await browser.newPage();
  page.on("console", (message) => { if (message.type() === "error" && !message.text().includes("Failed to load resource")) consoleErrors.push(message.text()); });
  page.on("pageerror", (error) => consoleErrors.push(`pageerror: ${error.message}`));
  await page.goto("http://localhost:1420", { waitUntil: "networkidle0", timeout: 40_000 });
  await page.waitForSelector(".nav", { timeout: 30_000 });
  await clickText(".nav", "Raw");
  await page.waitForFunction(() => document.querySelector(".raw-view h1")?.textContent?.includes("Raw Intake"));
  await clickText(".raw-view", "Scan / Rescan Raw");
  await page.waitForFunction(() => document.body.textContent?.includes("Raw scan COMPLETED: 0 entries observed"), { timeout: 20_000 });
  await screenshot("01-empty-raw.png");
  step("Empty Raw screen is explicit and scanning it does not create a source record");

  const raw = join(syntheticRoot, "Raw");
  writeFileSync(join(raw, "fixture-report.pdf"), Buffer.from("%PDF-1.4 UI fixture"));
  writeFileSync(join(raw, "fixture-report-copy.pdf"), Buffer.from("%PDF-1.4 UI fixture"));
  writeFileSync(join(raw, "fixture-image.jpg"), Buffer.from([0xff, 0xd8, 0xff, 0x00, 0x01]));
  writeFileSync(join(raw, "unknown.bin"), Buffer.from([0x00, 0x01, 0x02]));
  writeFileSync(join(raw, "WhatsApp export.txt"), "synthetic social export candidate");
  const rawBeforeScan = inventory(raw);
  await clickText(".raw-view", "Scan / Rescan Raw");
  await page.waitForFunction(() => document.querySelector(".raw-table")?.textContent?.includes("fixture-report.pdf"), { timeout: 20_000 });
  if (JSON.stringify(inventory(raw)) !== JSON.stringify(rawBeforeScan)) throw new Error("Raw scan changed synthetic source bytes.");
  const scanned = await request("/api/raw");
  if (scanned.counts.all !== 5 || scanned.counts.duplicates !== 2) throw new Error("Raw scanner did not retain the expected five synthetic records and duplicate group.");
  await screenshot("02-scan-results.png");
  step("Read-only scan renders deterministic classifications and separately retained exact duplicates");

  await clickText(".raw-filters", "Duplicates");
  await page.waitForFunction(() => document.querySelectorAll(".raw-table tbody tr").length === 2);
  await screenshot("03-duplicates.png");
  await clickText(".raw-filters", "All");
  await selectRaw("fixture-image.jpg");
  await page.waitForFunction(() => document.querySelector(".raw-detail")?.textContent?.includes("remains in Raw"));
  await screenshot("04-blocked-media.png");
  step("Media remains visibly blocked for a later phase and cannot be moved through this flow");

  await selectRaw("fixture-report.pdf");
  await setValue(".raw-detail input", "Database/Sources/ui-evidence/fixture-report.pdf");
  await page.$eval(".raw-detail textarea", (element) => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set.call(element, "Synthetic review evidence only.");
    element.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await clickText(".raw-detail", "Save correction");
  await page.waitForFunction(() => document.querySelector(".raw-detail")?.textContent?.includes("Human-selected generic provenance destination"));
  await screenshot("05-human-correction-ready.png");
  await clickText(".raw-detail", "Approve proposal");
  await page.waitForFunction(() => document.querySelector(".modal")?.textContent?.includes("Approve Raw proposal"));
  await screenshot("06-approval-explains-no-move.png");
  await clickText(".modal", "Record approval");
  await page.waitForFunction(() => [...document.querySelectorAll(".raw-detail button")].some((button) => button.textContent?.includes("Move approved file") && !button.disabled), { timeout: 20_000 });
  await screenshot("07-approved-ready-to-move.png");
  await clickText(".raw-detail", "Move approved file");
  await page.waitForFunction(() => document.querySelector(".raw-detail")?.textContent?.includes("MOVED"), { timeout: 20_000 });
  if (existsSync(join(raw, "fixture-report.pdf"))) throw new Error("Approved source remained in Raw after verified move.");
  if (readFileSync(join(syntheticRoot, "Database/Sources/ui-evidence/fixture-report.pdf")).toString() !== "%PDF-1.4 UI fixture") throw new Error("Verified destination payload is incorrect.");
  await screenshot("08-moved-with-provenance.png");
  step("Human correction, explicit approval, and verified move work end-to-end with separate approval and move actions");

  await page.click(".theme-toggle");
  await page.waitForFunction(() => document.documentElement.dataset.theme === "dark");
  await screenshot("09-dark-mode.png");
  if (consoleErrors.length) throw new Error(`Browser console errors: ${consoleErrors.join(" | ")}`);
  assertProductionUntouched();
  step("Raw screen remains usable in dark mode and the synthetic test preserved production data");
  console.log(`Raw UI E2E passed (${steps} checks).`);
} finally {
  if (browser) await browser.close().catch(() => undefined);
  stop(vite);
  stop(backend);
  if (sandbox.startsWith(resolve(tmpdir()))) rmSync(sandbox, { recursive: true, force: true });
}
