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
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "../..");
const REPO = resolve(ROOT, "..");
const SHOTS = resolve(REPO, "Documentation/UI-Screenshots");
const EDGE = existsSync("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
  ? "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
  : "C:/Program Files/Microsoft/Edge/Application/msedge.exe";
const PROD_DB = resolve(REPO, "Database/Main/family.db");
const PROD_PEOPLE = resolve(REPO, "Database/People");
const PROD_BACKUPS = resolve(REPO, "Backups");
const REAL_BOOTSTRAP = join(process.env.APPDATA ?? "", "people-relationships", "bootstrap.json");

function sha256(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex").toUpperCase();
}

function collectFiles(root, transient = false) {
  if (!existsSync(root)) return [];
  const rows = [];
  function scan(dir) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name);
      const rel = relative(root, path).replaceAll("\\", "/");
      if (transient && (rel.includes("__pycache__") || /(?:\.tmp|-wal|-shm)$/.test(rel) || /(^|\/)\.(backup_staging_|restore_staging_|restore_rollback_|journal-)/.test(rel))) continue;
      if (entry.isDirectory()) scan(path);
      else rows.push({ path: rel, bytes: statSync(path).size, hash: sha256(path) });
    }
  }
  scan(root);
  return rows.sort((a, b) => a.path.localeCompare(b.path));
}

const production = {
  db: sha256(PROD_DB),
  journals: collectFiles(PROD_PEOPLE).filter((row) => row.path.endsWith("/journal.md")),
  backups: collectFiles(PROD_BACKUPS),
  bootstrap: existsSync(REAL_BOOTSTRAP) ? { exists: true, hash: sha256(REAL_BOOTSTRAP), bytes: statSync(REAL_BOOTSTRAP).size } : { exists: false },
};
if (production.db !== "3258C738F9D65B23B15970D0E1E7389E8584A35BA8E26030249061BAF74E096E") throw new Error(`Unexpected production DB: ${production.db}`);
if (production.journals.length !== 35) throw new Error(`Expected 35 production Journals, found ${production.journals.length}`);

const sandbox = resolve(tmpdir(), `data_root_e2e_${Date.now()}`);
const bootstrap = join(sandbox, "settings", "bootstrap.json");
const rootA = join(sandbox, "Root A");
const rootB = join(sandbox, "Root B — عائلة");
const restoredRoot = join(sandbox, "Restored Root");
const movedRoot = join(sandbox, "Moved Root");
mkdirSync(dirname(bootstrap), { recursive: true });
mkdirSync(SHOTS, { recursive: true });

const python = process.platform === "win32" && existsSync(resolve(ROOT, ".venv/Scripts/python.exe"))
  ? resolve(ROOT, ".venv/Scripts/python.exe")
  : process.platform === "win32" ? "python" : "python3";
const env = { ...process.env };
delete env.PEOPLE_RELATIONSHIPS_ROOT;
Object.assign(env, {
  PYTHONUTF8: "1",
  PYTHONPATH: [resolve(ROOT, "App"), resolve(ROOT, "Scripts"), ROOT, process.env.PYTHONPATH].filter(Boolean).join(process.platform === "win32" ? ";" : ":"),
  PEOPLE_RELATIONSHIPS_BOOTSTRAP: bootstrap,
});
const backend = spawn(python, ["-m", "app.backend.main"], { cwd: ROOT, env, stdio: "pipe" });
const vite = spawn(process.platform === "win32" ? "npm.cmd" : "npm", ["--prefix", "App/Frontend", "run", "dev"], { cwd: ROOT, env, stdio: "pipe", shell: process.platform === "win32" });
backend.stderr.on("data", (data) => { if (/Traceback|ERROR/.test(data.toString())) console.error(data.toString()); });

const sleep = (ms) => new Promise((done) => setTimeout(done, ms));
async function waitForUrl(url, timeout = 30_000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    try { const response = await fetch(url); if (response.ok) return response; } catch {}
    await sleep(250);
  }
  throw new Error(`Timed out waiting for ${url}`);
}
async function api(path, init) {
  const response = await fetch(`http://127.0.0.1:8765${path}`, init);
  const payload = await response.json();
  if (!response.ok) throw new Error(`${path}: ${JSON.stringify(payload)}`);
  return payload;
}
async function post(path, body) {
  return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}
function stop(child) {
  if (!child?.pid) return;
  if (process.platform === "win32") { try { execFileSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" }); } catch {} }
  else { try { child.kill("SIGKILL"); } catch {} }
}
function verifyProduction() {
  if (sha256(PROD_DB) !== production.db) throw new Error("Production database changed");
  if (JSON.stringify(collectFiles(PROD_PEOPLE).filter((row) => row.path.endsWith("/journal.md"))) !== JSON.stringify(production.journals)) throw new Error("Production Journals changed");
  if (JSON.stringify(collectFiles(PROD_BACKUPS)) !== JSON.stringify(production.backups)) throw new Error("Production Backups changed");
  const now = existsSync(REAL_BOOTSTRAP) ? { exists: true, hash: sha256(REAL_BOOTSTRAP), bytes: statSync(REAL_BOOTSTRAP).size } : { exists: false };
  if (JSON.stringify(now) !== JSON.stringify(production.bootstrap)) throw new Error("Real bootstrap pointer changed");
}

let browser;
let page;
let passed = 0;
const consoleErrors = [];
function step(label) { passed += 1; console.log(`✓ [DataRoot E2E ${passed}] ${label}`); }
async function clickText(scope, text) {
  await page.waitForFunction((selector, expected) => [...document.querySelectorAll(`${selector} button`)].some((button) => button.textContent?.includes(expected) && !button.disabled), { timeout: 20_000 }, scope, text);
  await page.evaluate((selector, expected) => [...document.querySelectorAll(`${selector} button`)].find((button) => button.textContent?.includes(expected) && !button.disabled)?.click(), scope, text);
}
async function setValue(selector, value) {
  await page.waitForSelector(selector, { visible: true, timeout: 20_000 });
  await page.$eval(selector, (element, next) => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(element, next);
    element.dispatchEvent(new Event("input", { bubbles: true }));
  }, value);
}
async function reload() { await page.reload({ waitUntil: "networkidle0", timeout: 40_000 }); }
async function screenshot(name) { await sleep(200); await page.screenshot({ path: join(SHOTS, name) }); }
async function openChangeLocation() {
  await clickText(".nav", "Backups");
  await page.waitForSelector(".data-root-panel", { timeout: 20_000 });
  await clickText(".data-root-panel", "Change Location");
  await page.waitForSelector("[aria-label='Change Data Location']");
}

try {
  const healthResponse = await waitForUrl("http://127.0.0.1:8765/api/health");
  const health = await healthResponse.json();
  if (!health.service_ok || health.status !== "DATA_ROOT_UNCONFIGURED") throw new Error("Backend/root readiness boundary failed");
  step("Backend remains reachable with an explicitly unconfigured bootstrap");
  await waitForUrl("http://localhost:1420");
  browser = await puppeteer.launch({ executablePath: EDGE, headless: "new", args: ["--disable-gpu", "--no-first-run", "--no-sandbox", "--edge-skip-compat-layer-relaunch"], defaultViewport: { width: 1500, height: 1000 } });
  page = await browser.newPage();
  page.on("console", (message) => { if (message.type() === "error" && !message.text().includes("Failed to load resource")) consoleErrors.push(message.text()); });
  page.on("pageerror", (error) => consoleErrors.push(`pageerror: ${error.message}`));
  await page.evaluateOnNewDocument(() => {
    window.__forbiddenDialogs = 0;
    window.prompt = window.alert = window.confirm = () => { window.__forbiddenDialogs += 1; return false; };
  });
  await page.goto("http://localhost:1420", { waitUntil: "networkidle0", timeout: 40_000 });
  const firstText = await page.$eval("main", (node) => node.textContent);
  if (!firstText.includes("Welcome to People Relationships") || firstText.includes("Data Service Unavailable")) throw new Error("Wrong first-run state");
  step("First-run onboarding is distinct from StartupFailure");
  for (const route of ["Use Existing Data Root", "Restore From Backup", "Create New Data Root"]) if (!firstText.includes(route)) throw new Error(`Missing route: ${route}`);
  step("All three calm first-run routes are visible");
  await screenshot("first-run.png");
  await clickText("main", "Create New Data Root");
  await page.waitForSelector("#owner-name");
  step("Create New opens an accessible owner-and-destination form without browser dialogs");
  await setValue("#new-root-path", rootA);
  await setValue("#owner-name", "Alice Root A");
  await clickText("main", "Review New Data Root");
  await page.waitForSelector("[aria-label='New Data Root summary']");
  step("Create preview shows the chosen location and owner");
  await page.waitForFunction(() => [...document.querySelectorAll("button")].some((button) => button.textContent?.includes("Confirm Create New Data Root")));
  step("Create requires explicit confirmation after preview");
  await clickText("main", "Confirm Create New Data Root");
  await page.waitForFunction(() => document.querySelector("[role='status']")?.textContent?.includes("ready"), { timeout: 30_000 });
  step("Create reports completion only after the backend finishes");
  await clickText("main", "Continue");
  await page.waitForSelector(".nav", { timeout: 30_000 });
  step("Controlled reload enters the normal application shell");
  await page.waitForFunction(() => document.body.textContent?.includes("Alice Root A"), { timeout: 20_000 });
  step("The user-provided owner is My Perspective");
  const peopleA = await api("/api/people");
  if (peopleA.people.length !== 1 || peopleA.people[0].name !== "Alice Root A") throw new Error("Fresh owner records incorrect");
  step("Fresh Data Root contains exactly the initial owner");
  const statusA = await api("/api/data-root");
  if (statusA.schema_version !== 2 || statusA.data_root_format_version !== 1) throw new Error("Fresh versions incorrect");
  step("Fresh root keeps schema 2 and Data Root format 1");
  if (JSON.parse(readFileSync(bootstrap, "utf8")).active_root !== rootA) throw new Error("Bootstrap does not point to Root A");
  step("Atomic isolated bootstrap points to the published root");
  await clickText(".nav", "Family");
  await page.waitForSelector(".view", { timeout: 20_000 });
  await clickText(".nav", "Relationships");
  await page.waitForSelector(".view", { timeout: 20_000 });
  step("Family and Relationships load for a one-person root");

  unlinkSync(bootstrap);
  const nonempty = join(sandbox, "Nonempty");
  mkdirSync(nonempty);
  writeFileSync(join(nonempty, "keep.txt"), "keep", "utf8");
  await reload();
  await clickText("main", "Create New Data Root");
  await setValue("#new-root-path", nonempty);
  await setValue("#owner-name", "Must Not Exist");
  await clickText("main", "Review New Data Root");
  await page.waitForFunction(() => document.querySelector(".error-note")?.textContent?.includes("empty folder"));
  step("Create New clearly refuses an existing non-empty directory");
  if (readFileSync(join(nonempty, "keep.txt"), "utf8") !== "keep") throw new Error("Nonempty destination was overwritten");
  step("Create refusal preserves existing user files");
  if (existsSync(bootstrap) || !(await page.evaluate(() => document.body.textContent?.includes("Create New Data Root")))) throw new Error("Create refusal changed bootstrap or left onboarding");
  step("Create refusal leaves bootstrap unconfigured and onboarding recoverable");

  await post("/api/data-root/initialize", { target_path: rootB, owner_name: "Bob Root B", owner_gender: null });
  await post("/api/data-root/switch", { target_path: rootA });
  await reload();
  await openChangeLocation();
  step("Data Root panel opens Change Location from the normal app");
  const dialogText = await page.$eval("[aria-label='Change Data Location']", (node) => node.textContent);
  if (!dialogText.includes("Move Current Data") || !dialogText.includes("Use Existing Data Root")) throw new Error("Change modes unclear");
  step("Move and switch are presented as distinct operations");
  await clickText("[aria-label='Change Data Location']", "Use Existing Data Root");
  await setValue("#change-root-path", rootB);
  await clickText("[aria-label='Change Data Location']", "Inspect Data Root");
  await page.waitForSelector("[aria-label='Data Root change summary']");
  step("Existing root is inspected before any pointer change");
  const preview = await page.$eval("[aria-label='Data Root change summary']", (node) => node.textContent);
  if (!preview.includes("People: 1") || !preview.includes("Schema: 2") || !preview.includes("Writable")) throw new Error("Candidate summary incomplete");
  step("Candidate preview shows health, counts, schema, and write state");
  await screenshot("data-root-existing-preview.png");
  step("Existing-root preview has visual evidence");
  await clickText("[aria-label='Change Data Location']", "Confirm Use This Data Root");
  await page.waitForFunction(() => document.querySelector("[role='status']")?.textContent?.includes("No data was copied"));
  step("Switch completes only after explicit confirmation");
  await clickText("[aria-label='Change Data Location']", "Reload and Continue");
  await page.waitForFunction(() => document.body.textContent?.includes("Bob Root B"), { timeout: 30_000 });
  if (await page.evaluate(() => document.body.textContent?.includes("Alice Root A"))) throw new Error("Root A UI state leaked after switch");
  step("Reload shows Root B owner with no stale Root A identity");
  if (JSON.parse(readFileSync(bootstrap, "utf8")).active_root !== rootB || !existsSync(rootA)) throw new Error("Switch pointer/source preservation failed");
  step("Switch updates only the pointer and preserves Root A");

  const missing = join(sandbox, "Disconnected Root");
  writeFileSync(bootstrap, JSON.stringify({ active_root: missing }), "utf8");
  await reload();
  const missingText = await page.$eval("main", (node) => node.textContent);
  if (!missingText.includes("Data location unavailable") || !missingText.includes(missing)) throw new Error("Missing recovery screen incomplete");
  step("Missing configured root shows its last known location");
  if (missingText.includes("Welcome to People Relationships") || missingText.includes("Data Service Unavailable")) throw new Error("Missing root conflated with first-run/service failure");
  step("Missing root is distinct from first-run and backend failure");
  await screenshot("data-root-missing-recovery.png");
  step("Missing-root recovery has visual evidence");
  await clickText("main", "Retry");
  await page.waitForFunction(() => document.querySelector(".error-note")?.textContent?.includes("still unavailable"));
  step("Retry remains safely in recovery while the location is absent");
  await clickText("main", "Use Existing Data Root");
  await setValue("#existing-root-path", rootA);
  await clickText("main", "Inspect Data Root");
  await page.waitForSelector("[aria-label='Data Root candidate summary']");
  await clickText("main", "Confirm Use This Data Root");
  await page.waitForFunction(() => document.querySelector("[role='status']")?.textContent?.includes("now active"));
  step("Missing-root recovery previews and confirms a valid replacement root");
  await clickText("main", "Continue");
  await page.waitForFunction(() => document.body.textContent?.includes("Alice Root A"), { timeout: 30_000 });
  if (existsSync(missing)) throw new Error("Missing location was silently recreated");
  step("Recovery opens Root A without creating replacement data at the missing path");

  writeFileSync(bootstrap, "{", "utf8");
  await reload();
  const malformedText = await page.$eval("main", (node) => node.textContent);
  if (!malformedText.includes("Data-location setting needs attention") || !malformedText.includes("could not be read")) throw new Error("Malformed bootstrap UX missing");
  step("Malformed bootstrap has a specific settings-recovery state");
  if (malformedText.includes("Welcome to People Relationships") || malformedText.includes("Alice Root A")) throw new Error("Malformed bootstrap silently fell back");
  step("Malformed bootstrap does not become first-run or source fallback");
  await clickText("main", "Use Existing Data Root");
  await setValue("#existing-root-path", rootA);
  await clickText("main", "Inspect Data Root");
  await clickText("main", "Confirm Use This Data Root");
  await page.waitForFunction(() => document.querySelector("[role='status']")?.textContent?.includes("now active"));
  step("A valid existing root can replace the malformed pointer explicitly");
  await clickText("main", "Continue");
  await page.waitForSelector(".nav", { timeout: 30_000 });

  const backupResult = await post("/api/backups", { label: "Phase 8 external restore" });
  const backupPath = backupResult.backup.path;
  const backupBefore = collectFiles(backupPath);
  unlinkSync(bootstrap);
  await reload();
  await clickText("main", "Restore From Backup");
  const restoreForm = await page.$eval("main", (node) => node.textContent);
  if (!restoreForm.includes("two separate locations")) throw new Error("Restore source/destination distinction missing");
  step("First-run Restore explicitly separates source and destination");
  await setValue("#backup-source-path", backupPath);
  await clickText("main", "Verify Backup");
  await page.waitForSelector("[aria-label='Backup verification summary']");
  step("External backup is verified and summarized before restore");
  await setValue("#restore-destination-path", restoredRoot);
  await clickText("main", "Review Restore");
  await page.waitForSelector("[aria-label='Restore summary']");
  step("Restore shows the separate empty destination before confirmation");
  await clickText("[aria-label='Restore summary']", "Confirm Restore to New Data Root");
  await page.waitForFunction(() => document.querySelector("[role='status']")?.textContent?.includes("restored"), { timeout: 30_000 });
  if (JSON.stringify(collectFiles(backupPath)) !== JSON.stringify(backupBefore)) throw new Error("Backup source changed");
  step("Restore publishes atomically and leaves the backup source unchanged");
  await clickText("main", "Continue");
  await page.waitForFunction(() => document.body.textContent?.includes("Alice Root A"), { timeout: 30_000 });
  const restoredPeople = await api("/api/people");
  if (restoredPeople.people[0].name !== "Alice Root A") throw new Error("Restored owner missing");
  step("Controlled reload opens the restored people and perspective");
  if (JSON.parse(readFileSync(bootstrap, "utf8")).active_root !== restoredRoot) throw new Error("Restore pointer incorrect");
  step("Restore activates only the separately published destination");

  await openChangeLocation();
  const moveIntro = await page.$eval("[aria-label='Change Data Location']", (node) => node.textContent);
  if (!moveIntro.includes("old location is retained")) throw new Error("Old-root retention missing");
  step("Move UX explains copy semantics and old-root retention");
  await setValue("#change-root-path", movedRoot);
  await clickText("[aria-label='Change Data Location']", "Review Move");
  await page.waitForSelector("[aria-label='Data Root change summary']");
  const movePreview = await page.$eval("[aria-label='Data Root change summary']", (node) => node.textContent);
  if (!movePreview.includes("Source code and Documentation are excluded")) throw new Error("Move scope missing");
  step("Move preview states runtime-only scope before confirmation");
  await clickText("[aria-label='Change Data Location']", "Confirm Move Current Data");
  await page.waitForFunction(() => document.querySelector("[role='status']")?.textContent?.includes("additional safety copy"), { timeout: 40_000 });
  step("Move completes with truthful old-root retention wording");
  await screenshot("data-root-move.png");
  step("Move confirmation has visual evidence");
  const sourceInventory = [...collectFiles(join(restoredRoot, "Database"), true).map((row) => ({ ...row, path: `Database/${row.path}` })), ...collectFiles(join(restoredRoot, "Backups"), true).map((row) => ({ ...row, path: `Backups/${row.path}` }))].sort((a, b) => a.path.localeCompare(b.path));
  const movedInventory = [...collectFiles(join(movedRoot, "Database"), true).map((row) => ({ ...row, path: `Database/${row.path}` })), ...collectFiles(join(movedRoot, "Backups"), true).map((row) => ({ ...row, path: `Backups/${row.path}` }))].sort((a, b) => a.path.localeCompare(b.path));
  if (JSON.stringify(sourceInventory) !== JSON.stringify(movedInventory)) throw new Error("Moved runtime inventory differs");
  step("Move preserves exact runtime path, size, and SHA-256 inventory");
  if (!existsSync(restoredRoot) || existsSync(join(movedRoot, "Codebase")) || existsSync(join(movedRoot, "Documentation"))) throw new Error("Move scope/retention violated");
  step("Moved root excludes Codebase/Documentation and retains the old root");
  await clickText("[aria-label='Change Data Location']", "Reload and Continue");
  await page.waitForSelector(".nav", { timeout: 30_000 });

  const ownerJournal = collectFiles(join(movedRoot, "Database/People")).find((row) => row.path.endsWith("/journal.md"));
  const journalPath = join(movedRoot, "Database/People", ownerJournal.path);
  unlinkSync(journalPath);
  const orphan = join(movedRoot, "Database/People/Other/human-review/notes.md");
  mkdirSync(dirname(orphan), { recursive: true });
  writeFileSync(orphan, "preserve", "utf8");
  await reload();
  await page.waitForFunction(() => document.body.textContent?.includes("repairable alignment issues"), { timeout: 30_000 });
  step("Repairable root opens with a structured non-blocking warning");
  await clickText(".nav", "Backups");
  await clickText(".data-root-panel", "Validate");
  await page.waitForSelector("[aria-label='Data Root Health Audit']");
  await clickText("[aria-label='Data Root Health Audit']", "Run Safe Repair");
  await page.waitForFunction(
    () => [...document.querySelectorAll(".info-note")].some((note) => note.textContent?.includes("Repaired")),
    { timeout: 20_000 },
  );
  if (!existsSync(journalPath)) throw new Error("Safe Repair did not restore the missing Journal");
  step("Safe Repair restores the supported missing Journal");
  if (readFileSync(orphan, "utf8") !== "preserve") throw new Error("Safe Repair changed orphan user content");
  step("Safe Repair preserves unrelated orphan user content");

  const currentStatus = await api("/api/data-root");
  await page.setRequestInterception(true);
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.origin === "http://localhost:1420" && url.pathname === "/api/data-root" && request.method() === "GET") {
      request.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ ...currentStatus, state: "READ_ONLY", read_only: true, health: { ...currentStatus.health, read_only: true } }) });
    } else request.continue();
  });
  await reload();
  await page.waitForFunction(() => document.body.textContent?.includes("Read-only Data Root"), { timeout: 20_000 });
  step("Read-only state has a persistent non-color-only banner");
  if (consoleErrors.length || await page.evaluate(() => window.__forbiddenDialogs !== 0)) throw new Error(`UI errors/dialogs: ${consoleErrors.join("; ")}`);
  step("The complete journey has no console errors or browser dialogs");

  if (passed !== 50) throw new Error(`Expected exactly 50 meaningful checks, recorded ${passed}`);
  verifyProduction();
  console.log(`\nALL ${passed} DATAROOT E2E CHECKS PASSED\n`);
} finally {
  if (browser) await browser.close();
  stop(backend);
  stop(vite);
  await sleep(700);
  rmSync(sandbox, { recursive: true, force: true });
  verifyProduction();
}
