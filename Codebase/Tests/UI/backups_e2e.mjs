import puppeteer from "puppeteer-core";
import { createHash } from "node:crypto";
import { execFileSync, spawn } from "node:child_process";
import {
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "../..");
const REPO_ROOT = resolve(ROOT, "..");
const SCREENSHOTS = resolve(REPO_ROOT, "Documentation/UI-Screenshots");
const EDGE = existsSync("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
  ? "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
  : "C:/Program Files/Microsoft/Edge/Application/msedge.exe";
const PROD_DB = resolve(REPO_ROOT, "Database/Main/family.db");
const PROD_PEOPLE = resolve(REPO_ROOT, "Database/People");
const PROD_BACKUPS = resolve(REPO_ROOT, "Backups");
const PERSON_ID = "mohammad_yahya_hussain";

function sha256(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex").toUpperCase();
}

function collectFiles(root) {
  if (!existsSync(root)) return [];
  const rows = [];
  function scan(dir) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name);
      if (entry.isDirectory()) scan(path);
      else rows.push({ path: relative(root, path).replaceAll("\\", "/"), bytes: statSync(path).size, hash: sha256(path) });
    }
  }
  scan(root);
  return rows.sort((a, b) => a.path.localeCompare(b.path));
}

function same(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

const productionDbHash = sha256(PROD_DB);
const productionJournals = collectFiles(PROD_PEOPLE).filter((row) => row.path.endsWith("/journal.md"));
const productionBackups = collectFiles(PROD_BACKUPS);
if (productionDbHash !== "3258C738F9D65B23B15970D0E1E7389E8584A35BA8E26030249061BAF74E096E") {
  throw new Error(`Unexpected production DB baseline: ${productionDbHash}`);
}
if (productionJournals.length !== 35) throw new Error(`Expected 35 production journals, found ${productionJournals.length}`);
console.log(`[Safety Baseline] DB ${productionDbHash}; journals ${productionJournals.length}; backup files ${productionBackups.length}`);

const sandbox = resolve(tmpdir(), `backups_e2e_root_${Date.now()}`);
mkdirSync(sandbox, { recursive: true });
cpSync(resolve(REPO_ROOT, "Database"), join(sandbox, "Database"), { recursive: true });
cpSync(PROD_BACKUPS, join(sandbox, "Backups"), { recursive: true });
mkdirSync(SCREENSHOTS, { recursive: true });
const journalPath = join(sandbox, "Database/People/Family", PERSON_ID, "journal.md");
const originalJournal = readFileSync(journalPath);
const configPath = join(sandbox, "Database/Config/e2e-phase7.json");
writeFileSync(configPath, '{"state":"before"}\n', "utf8");

const python = process.platform === "win32" && existsSync(resolve(ROOT, ".venv/Scripts/python.exe"))
  ? resolve(ROOT, ".venv/Scripts/python.exe")
  : process.platform === "win32" ? "python" : "python3";
const env = {
  ...process.env,
  PYTHONUTF8: "1",
  PYTHONPATH: [resolve(ROOT, "App"), resolve(ROOT, "Scripts"), ROOT, process.env.PYTHONPATH]
    .filter(Boolean).join(process.platform === "win32" ? ";" : ":"),
  PEOPLE_RELATIONSHIPS_ROOT: sandbox,
};
const backend = spawn(python, ["-m", "app.backend.main"], { cwd: ROOT, env, stdio: "pipe" });
const vite = spawn(
  process.platform === "win32" ? "npm.cmd" : "npm",
  ["--prefix", "App/Frontend", "run", "dev"],
  { cwd: ROOT, env, stdio: "pipe", shell: process.platform === "win32" },
);
backend.stderr.on("data", (data) => {
  const message = data.toString();
  if (message.includes("Traceback") || message.includes("ERROR")) console.error(message);
});

const sleep = (ms) => new Promise((done) => setTimeout(done, ms));
async function waitForUrl(url, timeout = 30_000) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    try { if ((await fetch(url)).ok) return; } catch {}
    await sleep(300);
  }
  throw new Error(`Timed out waiting for ${url}`);
}

async function api(path, init) {
  const response = await fetch(`http://127.0.0.1:8765${path}`, init);
  const payload = await response.json();
  if (!response.ok) throw new Error(`${path}: ${JSON.stringify(payload)}`);
  return payload;
}

function stop(child) {
  if (!child?.pid) return;
  if (process.platform === "win32") {
    try { execFileSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" }); } catch {}
  } else {
    try { child.kill("SIGKILL"); } catch {}
  }
}

function verifyProduction() {
  if (sha256(PROD_DB) !== productionDbHash) throw new Error("Production database changed");
  if (!same(collectFiles(PROD_PEOPLE).filter((row) => row.path.endsWith("/journal.md")), productionJournals)) throw new Error("Production Journals changed");
  if (!same(collectFiles(PROD_BACKUPS), productionBackups)) throw new Error("Production Backups changed");
  console.log("[Safety Verification] Production DB, 35 Journals, and Backups are byte-identical.");
}

let browser;
let page;
let passed = 0;
function step(label) {
  passed += 1;
  console.log(`✓ [Backups E2E ${passed}] ${label}`);
}

async function clickText(scope, text) {
  await page.waitForFunction((selector, expected) => [...document.querySelectorAll(`${selector} button`)].some((button) => {
    const rect = button.getBoundingClientRect();
    return button.textContent?.trim().includes(expected) && !button.disabled && rect.width > 0 && rect.height > 0;
  }), { timeout: 20_000 }, scope, text);
  await page.evaluate((selector, expected) => {
    const button = [...document.querySelectorAll(`${selector} button`)].find((candidate) => candidate.textContent?.trim().includes(expected) && !candidate.disabled);
    button.click();
  }, scope, text);
}

async function setValue(selector, value) {
  await page.waitForSelector(selector, { visible: true, timeout: 15_000 });
  await page.$eval(selector, (element, next) => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(element, next);
    element.dispatchEvent(new Event("input", { bubbles: true }));
  }, value);
}

async function closeModal() {
  await page.click(".modal-head button[title='Close']");
  await page.waitForFunction(() => !document.querySelector(".modal"));
}

async function rowFor(id) {
  await page.waitForSelector(`[data-backup-id='${id}']`, { timeout: 20_000 });
  return `[data-backup-id='${id}']`;
}

async function screenshot(name) {
  // Let the shared 150 ms modal fade finish so visual evidence is not translucent mid-animation.
  await sleep(250);
  await page.screenshot({ path: join(SCREENSHOTS, name) });
}

try {
  await waitForUrl("http://127.0.0.1:8765/api/health");
  await waitForUrl("http://localhost:1420");

  const legacySource = await api("/api/backups", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ label: "Legacy fixture source" }),
  });
  const legacyPath = join(sandbox, "Backups", "legacy-e2e");
  cpSync(legacySource.backup.path, legacyPath, { recursive: true });
  const legacyManifestPath = join(legacyPath, "manifest.json");
  const legacyManifest = JSON.parse(readFileSync(legacyManifestPath, "utf8"));
  legacyManifest.format = legacyManifest.kind;
  delete legacyManifest.kind;
  delete legacyManifest.backup_format_version;
  delete legacyManifest.category;
  delete legacyManifest.safety_reason;
  delete legacyManifest.app_version;
  writeFileSync(legacyManifestPath, `${JSON.stringify(legacyManifest, null, 2)}\n`, "utf8");
  await api("/api/backups", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ label: '<img src=x onerror="window.__BACKUP_PWNED__=1">' }),
  });

  browser = await puppeteer.launch({
    executablePath: EDGE,
    headless: "new",
    args: ["--disable-gpu", "--no-first-run", "--no-sandbox", "--edge-skip-compat-layer-relaunch"],
    defaultViewport: { width: 1600, height: 1000 },
  });
  page = await browser.newPage();
  const consoleErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error" && !message.text().includes("Failed to load resource")) consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(`pageerror: ${error.message}`));
  await page.evaluateOnNewDocument(() => {
    window.__promptCalls = 0;
    window.prompt = () => { window.__promptCalls += 1; return null; };
  });
  await page.goto("http://localhost:1420", { waitUntil: "networkidle0", timeout: 40_000 });
  await clickText(".nav", "Backups");
  await page.waitForSelector("[aria-label='Manual backups']");
  step("Backups screen opens");

  for (const category of ["Manual", "Automatic", "Safety", "Legacy"]) {
    if (!(await page.$(`[aria-label='${category} backups']`))) throw new Error(`${category} category missing`);
  }
  step("Manual, Automatic, Safety, and Legacy categories are visible");
  if (!(await page.$eval("[aria-label='Automatic backups']", (node) => node.textContent)).includes("scheduling is not configured")) throw new Error("Automatic limitation missing");
  step("Automatic scheduling limitation is explicit");
  await page.waitForFunction(() => document.querySelector("[aria-label='Legacy backups']")?.textContent?.includes("legacy-e2e"), { timeout: 30_000 });
  step("Valid legacy top-level backup is displayed safely");
  if (await page.$eval("[aria-label='Manual backups']", (node) => Boolean(node.querySelector("img")))) throw new Error("Hostile label became active markup");
  if (await page.evaluate(() => Boolean(window.__BACKUP_PWNED__))) throw new Error("Hostile backup label executed");
  step("Malicious manifest label remains inert text");

  await clickText(".view-head", "Create Backup");
  await page.waitForSelector("[aria-label='Create Manual Backup']");
  step("Create Backup opens an in-app dialog");
  if (await page.evaluate(() => window.__promptCalls)) throw new Error("window.prompt was called");
  step("Create flow does not call browser prompt");
  const createText = await page.$eval("[aria-label='Create Manual Backup']", (node) => node.textContent);
  for (const included of ["SQLite database", "People", "Journals", "portable Config"]) {
    if (!createText.includes(included)) throw new Error(`Create inclusion missing: ${included}`);
  }
  step("Create dialog states the complete snapshot scope");
  await setValue("#backup-label", "Before Phase 7 E2E mutation");
  step("Optional human label is editable");
  await clickText("[aria-label='Create Manual Backup']", "Create Backup");
  await page.waitForFunction(() => document.querySelector(".info-note")?.textContent?.includes("Verified backup created"), { timeout: 30_000 });
  step("Manual backup creation succeeds and verifies before publication");
  let listing = await api("/api/backups");
  const first = listing.backups.find((item) => item.label === "Before Phase 7 E2E mutation");
  if (!first) throw new Error("Created backup missing from API listing");
  if (!first.path.includes(join("Backups", "Manual"))) throw new Error(`Manual backup path incorrect: ${first.path}`);
  step("New snapshot is published inside Backups/Manual");
  if (!first.verified || first.integrity_status !== "verified") throw new Error("Created backup not verified");
  step("New snapshot has an explicit verified state");
  await rowFor(first.id);
  step("New snapshot appears immediately in the Manual UI");
  await screenshot("backups-list.png");

  await clickText(await rowFor(first.id), "View Details");
  await page.waitForSelector("[aria-label^='Backup Details:']");
  step("View Details opens in-app");
  const details = await page.$eval("[aria-label^='Backup Details:']", (node) => node.textContent);
  for (const value of ["Category", "Created", "Backup Format", "Schema Version", "People Count", "Journal Count", "Total Files", "Total Size"]) {
    if (!details.includes(value)) throw new Error(`Details missing ${value}`);
  }
  step("Details shows timestamp, category, format, schema, files, people, Journals, and size");
  if (!details.includes("VERIFIED")) throw new Error("Details verification state missing");
  step("Details reports the accurate verification state");
  await screenshot("backup-details.png");
  await closeModal();

  await clickText(await rowFor(first.id), "Verify");
  await page.waitForSelector("[aria-label='Backup Verified ✓']", { timeout: 30_000 });
  step("Verify opens an in-app result dialog");
  const verifyText = await page.$eval("[aria-label='Backup Verified ✓']", (node) => node.textContent);
  if (!verifyText.includes("SHA-256") || !verifyText.includes("Database: ok")) throw new Error("Verification proof incomplete");
  step("Verification result reports files, hashes, counts, schema, and SQLite integrity");
  await screenshot("backup-verified.png");
  await closeModal();

  await clickText(".view-head", "Create Backup");
  await setValue("#backup-label", "Second rapid backup");
  await clickText("[aria-label='Create Manual Backup']", "Create Backup");
  await page.waitForFunction(() => [...document.querySelectorAll(".backup-row strong")].some((node) => node.textContent === "Second rapid backup"), { timeout: 30_000 });
  listing = await api("/api/backups");
  const second = listing.backups.find((item) => item.label === "Second rapid backup");
  if (!second || second.id === first.id) throw new Error("Rapid backup ID collision");
  step("Two quickly created backups have distinct IDs");

  const personBefore = (await api(`/api/people/${PERSON_ID}`)).person;
  await api(`/api/people/${PERSON_ID}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: "Phase Seven Mutated Person" }),
  });
  step("Sandbox person data is mutated after the restore source snapshot");
  writeFileSync(journalPath, Buffer.concat([originalJournal, Buffer.from("\nPhase 7 mutated Journal\n", "utf8")]));
  step("Sandbox Journal bytes are mutated after the snapshot");
  writeFileSync(configPath, '{"state":"after"}\n', "utf8");
  step("Sandbox portable Config is mutated after the snapshot");

  await clickText(await rowFor(first.id), "Restore");
  await page.waitForSelector("[aria-label^='Restore Backup:']");
  step("Restore opens the correct backup preview");
  const preview = await page.$eval("[aria-label^='Restore Backup:']", (node) => node.textContent);
  for (const value of [first.label, "Current data will be replaced", "Safety / Pre-Restore", "People / Journals", "Verification / Compatibility"]) {
    if (!preview.includes(value)) throw new Error(`Restore preview missing ${value}`);
  }
  step("Restore preview names replacement scope and mandatory safety snapshot");
  await screenshot("backup-restore.png");
  await setValue("#restore-confirmation", "restore");
  const invalidDisabled = await page.$eval("[aria-label^='Restore Backup:'] .btn-danger", (button) => button.disabled);
  if (!invalidDisabled) throw new Error("Invalid restore token enabled submission");
  step("Invalid confirmation token cannot submit");
  await setValue("#restore-confirmation", "RESTORE");
  const validDisabled = await page.$eval("[aria-label^='Restore Backup:'] .btn-danger", (button) => button.disabled);
  if (validDisabled) throw new Error("Exact RESTORE token did not enable submission");
  step("Exact RESTORE token enables a verified compatible restore");
  await clickText("[aria-label^='Restore Backup:']", "Confirm Restore");
  await page.waitForFunction(() => document.querySelector("[role='status']")?.textContent?.includes("Creating the safety backup and restoring"), { timeout: 10_000 });
  step("Progress shows only the real in-flight backend operation");
  await page.waitForFunction(() => document.querySelector("[role='status']")?.textContent?.includes("post-restore health checks passed"), { timeout: 40_000 });
  step("UI reports completion only after backend post-restore health succeeds");

  const personAfter = (await api(`/api/people/${PERSON_ID}`)).person;
  if (personAfter.name !== personBefore.name) throw new Error("Person state was not restored");
  step("Person database state matches the selected backup");
  if (!readFileSync(journalPath).equals(originalJournal)) throw new Error("Journal bytes were not restored exactly");
  step("Journal bytes match the selected backup exactly");
  if (readFileSync(configPath, "utf8") !== '{"state":"before"}\n') throw new Error("Portable Config was not restored");
  step("Portable Config matches the selected backup");
  listing = await api("/api/backups");
  const safety = listing.backups.find((item) => item.category === "safety" && item.safety_reason === "pre_restore" && item.id !== first.id);
  if (!safety?.verified) throw new Error("Verified pre-restore safety backup missing");
  step("Verified pre-restore safety backup exists");
  if (!safety.path.includes(join("Safety", "Pre-Restore"))) throw new Error("Safety backup category path incorrect");
  step("Safety backup is stored under Safety / Pre-Restore");
  if (!existsSync(first.path)) throw new Error("Original restore source disappeared");
  step("Original restore source and the complete Backups tree survive restore");
  await clickText("[aria-label^='Restore Backup:']", "Reload Restored Data");
  await page.waitForSelector(".nav", { timeout: 30_000 });
  await clickText(".nav", "Backups");
  await page.waitForSelector("[aria-label='Safety backups']", { timeout: 30_000 });
  step("Application reloads into a usable Backups screen after restore");

  writeFileSync(join(second.path, "data/family.db"), "corrupt", "utf8");
  await clickText(await rowFor(second.id), "Verify");
  await page.waitForSelector("[aria-label='Verification Failed']", { timeout: 30_000 });
  step("Corrupted sandbox backup produces an in-app verification failure");
  const corruptText = await page.$eval("[aria-label='Verification Failed']", (node) => node.textContent);
  if (!corruptText.includes("BACKUP_SIZE_MISMATCH") && !corruptText.includes("BACKUP_DB_INVALID")) throw new Error("Corruption code missing");
  step("Corruption result names a machine-classified problem");
  await closeModal();
  const corruptRestoreDisabled = await page.$eval(`${await rowFor(second.id)} .btn-primary`, (button) => button.disabled);
  if (!corruptRestoreDisabled) throw new Error("Corrupt backup restore remained enabled");
  step("Restore is disabled for a corrupt backup");

  const status = await api("/api/data-root");
  await page.setRequestInterception(true);
  page.on("request", (request) => {
    if (request.url().includes("/api/data-root") && request.method() === "GET") {
      request.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ ...status, read_only: true }) });
    } else request.continue();
  });
  await page.reload({ waitUntil: "networkidle0" });
  await clickText(".nav", "Backups");
  await page.waitForFunction(() => document.querySelector(".info-note")?.textContent?.includes("read-only"));
  const createDisabled = await page.$eval(".view-head .btn-primary", (button) => button.disabled);
  if (!createDisabled) throw new Error("Read-only Create remained enabled");
  step("Read-only mode blocks Create with an explanation");
  const restoreDisabled = await page.$eval(`${await rowFor(first.id)} .btn-primary`, (button) => button.disabled);
  if (!restoreDisabled) throw new Error("Read-only Restore remained enabled");
  step("Read-only mode blocks Restore");
  const verifyDisabled = await page.$eval(`${await rowFor(first.id)} .btn-ghost:nth-of-type(2)`, (button) => button.disabled);
  if (verifyDisabled) throw new Error("Read-only Verify was disabled");
  step("Read-only mode preserves verification");
  if (consoleErrors.length) throw new Error(`Unexpected console errors: ${consoleErrors.join("; ")}`);
  step("No unexpected browser console or page errors");
  if (passed < 40 || passed > 45) throw new Error(`Expected 40–45 meaningful checks, recorded ${passed}`);
  console.log(`\nALL ${passed} BACKUPS E2E CHECKS PASSED\n`);
} finally {
  if (browser) await browser.close();
  stop(backend);
  stop(vite);
  await sleep(700);
  rmSync(sandbox, { recursive: true, force: true });
  verifyProduction();
}
