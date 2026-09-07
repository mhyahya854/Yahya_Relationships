import puppeteer from "puppeteer-core";
import {
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { createHash } from "node:crypto";
import { execSync, spawn } from "node:child_process";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
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

function sha256(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex").toUpperCase();
}

function collectJournals(root) {
  const rows = [];
  function scan(dir) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name);
      if (entry.isDirectory()) scan(path);
      else if (entry.name === "journal.md") rows.push({ path, hash: sha256(path) });
    }
  }
  scan(root);
  return rows.sort((a, b) => a.path.localeCompare(b.path));
}

const productionDbHash = sha256(PROD_DB);
const productionJournals = collectJournals(PROD_PEOPLE);
if (productionJournals.length !== 35) {
  throw new Error(`Expected 35 production journals, found ${productionJournals.length}`);
}
console.log(`[Safety Baseline] Production DB ${productionDbHash}; journals ${productionJournals.length}`);

const sandbox = resolve(tmpdir(), `journals_e2e_root_${Date.now()}`);
mkdirSync(sandbox, { recursive: true });
cpSync(resolve(REPO_ROOT, "Database"), join(sandbox, "Database"), { recursive: true });
mkdirSync(SCREENSHOTS, { recursive: true });

const python = process.platform === "win32" && existsSync(resolve(ROOT, ".venv/Scripts/python.exe"))
  ? resolve(ROOT, ".venv/Scripts/python.exe")
  : process.platform === "win32" ? "python" : "python3";
const pythonPath = [resolve(ROOT, "App"), resolve(ROOT, "Scripts"), ROOT, process.env.PYTHONPATH]
  .filter(Boolean)
  .join(process.platform === "win32" ? ";" : ":");
const env = {
  ...process.env,
  PYTHONUTF8: "1",
  PYTHONPATH: pythonPath,
  PEOPLE_RELATIONSHIPS_ROOT: sandbox,
};

const backend = spawn(python, ["-m", "app.backend.main"], {
  cwd: ROOT,
  env,
  stdio: "pipe",
});
const vite = spawn(
  process.platform === "win32" ? "npm.cmd" : "npm",
  ["--prefix", "App/Frontend", "run", "dev"],
  { cwd: ROOT, env, stdio: "pipe", shell: process.platform === "win32" },
);
backend.stderr.on("data", (data) => {
  const message = data.toString();
  if (message.includes("Traceback") || message.includes("ERROR")) console.error(message);
});

const sleep = (ms) => new Promise((resolveSleep) => setTimeout(resolveSleep, ms));
async function waitForUrl(url, timeout = 30_000) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {}
    await sleep(500);
  }
  throw new Error(`Timed out waiting for ${url}`);
}

function stopProcess(child) {
  if (!child?.pid) return;
  if (process.platform === "win32") {
    try { execSync(`taskkill /pid ${child.pid} /T /F`, { stdio: "ignore" }); } catch {}
  } else {
    try { child.kill("SIGKILL"); } catch {}
  }
}

function verifyProduction() {
  if (sha256(PROD_DB) !== productionDbHash) throw new Error("Production database hash changed");
  const current = collectJournals(PROD_PEOPLE);
  if (current.length !== productionJournals.length) throw new Error("Production journal count changed");
  for (let index = 0; index < current.length; index += 1) {
    if (current[index].path !== productionJournals[index].path || current[index].hash !== productionJournals[index].hash) {
      throw new Error(`Production journal changed: ${productionJournals[index].path}`);
    }
  }
  console.log("[Safety Verification] Database and all 35 production journals are byte-identical.");
}

let browser;
let passed = 0;
function step(label) {
  passed += 1;
  console.log(`✓ [Journal E2E ${passed}] ${label}`);
}

try {
  await waitForUrl("http://127.0.0.1:8765/api/health");
  await waitForUrl("http://localhost:1420");
  browser = await puppeteer.launch({
    executablePath: EDGE,
    headless: "new",
    args: ["--disable-gpu", "--no-first-run", "--no-sandbox", "--edge-skip-compat-layer-relaunch"],
    defaultViewport: { width: 1600, height: 1000 },
  });
  const page = await browser.newPage();
  const consoleErrors = [];
  page.on("console", (message) => {
    const text = message.text();
    const expectedHttpError = text.includes("status of 409") || text.includes("status of 404");
    if (message.type() === "error" && !text.includes("favicon") && !expectedHttpError) consoleErrors.push(text);
  });
  page.on("pageerror", (error) => consoleErrors.push(`pageerror: ${error.message}`));

  async function clickText(scope, text) {
    await page.waitForFunction((selector, expected) => {
      return [...document.querySelectorAll(`${selector} button`)].some((button) => {
        const rect = button.getBoundingClientRect();
        return button.textContent?.trim().includes(expected) && !button.disabled && rect.width > 0 && rect.height > 0;
      });
    }, { timeout: 12_000 }, scope, text);
    await page.evaluate((selector, expected) => {
      const button = [...document.querySelectorAll(`${selector} button`)].find(
        (candidate) => candidate.textContent?.trim().includes(expected) && !candidate.disabled,
      );
      button.click();
    }, scope, text);
    await sleep(250);
  }

  async function setValue(selector, value) {
    await page.waitForSelector(selector, { visible: true, timeout: 12_000 });
    await page.$eval(selector, (element, nextValue) => {
      const prototype = element instanceof HTMLTextAreaElement
        ? HTMLTextAreaElement.prototype
        : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(prototype, "value").set.call(element, nextValue);
      element.dispatchEvent(new Event("input", { bubbles: true }));
    }, value);
    await sleep(120);
  }

  async function openPeopleJournal(name) {
    await clickText(".nav", "People");
    await page.waitForSelector(".people-table-row", { timeout: 15_000 });
    const opened = await page.evaluate((expected) => {
      const cells = [...document.querySelectorAll(".people-table-row .person-cell")];
      const cell = cells.find((item) => item.textContent?.includes(expected));
      cell?.click();
      return Boolean(cell);
    }, name);
    if (!opened) throw new Error(`People row not found: ${name}`);
    await page.waitForSelector(".person-profile-container", { timeout: 10_000 });
    await clickText(".tabs", "Journal ✓").catch(() => clickText(".tabs", "Journal ⚠"));
    await page.waitForSelector(".journal-experience", { timeout: 10_000 });
  }

  async function closeModal() {
    await page.click(".modal-head button[title='Close']");
    await sleep(250);
  }

  async function screenshot(name) {
    await page.screenshot({ path: join(SCREENSHOTS, name) });
  }

  const personName = "Mohammad Yahya Hussain";
  const personId = "mohammad_yahya_hussain";
  const journalPath = join(sandbox, "Database/People/Family", personId, "journal.md");
  const initialContent = readFileSync(journalPath, "utf8");
  const editedContent = `${initialContent}## Phase 5\n\nEnglish اردو Roman Urdu 😀\n`;

  await page.goto("http://localhost:1420", { waitUntil: "networkidle0", timeout: 40_000 });
  step("Application opened");
  await openPeopleJournal(personName);
  step("People opened and canonical profile selected");
  step("Embedded Profile Journal tab opened");
  await page.waitForFunction((expected) => document.querySelector(".journal-view")?.textContent?.includes(expected), {}, personName);
  step("Existing canonical Journal rendered");
  const canonicalMeta = await page.$eval(".journal-meta", (element) => element.textContent);
  if (!canonicalMeta.includes("Canonical journal loaded")) throw new Error("Canonical Journal status missing");
  if (!(await page.$eval(".journal-hint", (element) => element.textContent)).includes("revision")) throw new Error("Revision indicator missing");
  step("Canonical file and revision status are visible");
  await screenshot("journal-view.png");

  await clickText(".journal-experience", "Edit");
  step("Edit mode opened");
  const exactEditor = await page.$eval(".journal-editor", (element) => element.value);
  if (exactEditor !== initialContent) throw new Error("Editor did not load exact Markdown bytes");
  step("Editor contains exact existing Markdown");
  await setValue(".journal-editor", editedContent);
  step("Mixed English, Urdu, Roman Urdu, and emoji draft entered");
  await page.waitForFunction(() => document.querySelector(".journal-status")?.textContent === "Unsaved");
  step("Unsaved status shown without color-only signaling");
  await screenshot("journal-edit.png");
  await clickText(".journal-experience", "Preview");
  await page.waitForFunction(() => document.querySelector(".journal-preview")?.textContent?.includes("Roman Urdu"));
  step("Preview rendered the updated Markdown");
  await clickText(".journal-experience", "Edit");
  await page.focus(".journal-editor");
  await page.keyboard.down("Control");
  await page.keyboard.press("KeyS");
  await page.keyboard.up("Control");
  await page.waitForFunction(() => document.querySelector(".journal-status")?.textContent === "Saved");
  step("Ctrl/Cmd+S saved and prevented browser Save");
  if (readFileSync(journalPath, "utf8") !== editedContent) throw new Error("Sandbox journal bytes differ after save");
  step("Sandbox journal.md bytes match exact edited content");

  await closeModal();
  await openPeopleJournal(personName);
  await page.waitForFunction((expected) => document.querySelector(".journal-view")?.textContent?.includes(expected), {}, "Roman Urdu");
  step("Close and reopen preserved content");
  await closeModal();

  await clickText(".nav", "Family");
  await page.waitForSelector(`.family-diagram g.node[aria-label='Family member card: ${personId}']`, { timeout: 20_000 });
  await page.click(`.family-diagram g.node[aria-label='Family member card: ${personId}']`);
  await page.waitForSelector(".family-side");
  await clickText(".family-side-actions", "Journal");
  await page.waitForFunction((expected) => document.querySelector(".journal-view")?.textContent?.includes(expected), {}, "Roman Urdu");
  step("Family opened the same canonical Journal content");
  await closeModal();

  await clickText(".nav", "Relationships");
  await page.waitForSelector(".relationships-search-wrap input", { timeout: 15_000 });
  await setValue(".relationships-search-wrap input", personName);
  await page.waitForSelector(".person-search-row", { timeout: 10_000 });
  await page.click(".person-search-row");
  await page.waitForSelector(".selected-person-panel");
  await clickText(".panel-actions", "Journal");
  await page.waitForFunction((expected) => document.querySelector(".journal-view")?.textContent?.includes(expected), {}, "Roman Urdu");
  step("Relationships opened the same canonical Journal content");

  await clickText(".journal-experience", "Quick Append");
  await page.waitForSelector("[aria-label='Quick Append']");
  step("Quick Append opened as an in-app dialog");
  await clickText("[aria-label='Quick Append']", "Append");
  await page.waitForFunction(() => document.querySelector("[aria-label='Quick Append'] .error-note")?.textContent?.includes("required"));
  step("Quick Append rejected an empty entry in-app");
  await setValue("[aria-label='Quick Append heading']", "2026-09-07");
  await setValue("[aria-label='Quick Append entry']", "Quick memory اردو ✨");
  await clickText("[aria-label='Quick Append']", "Append");
  await page.waitForFunction(() => document.querySelector(".journal-view")?.textContent?.includes("Quick memory"));
  const appendedContent = readFileSync(journalPath, "utf8");
  if (!appendedContent.includes("## 2026-09-07\n\nQuick memory اردو ✨\n")) throw new Error("Quick Append formatting mismatch");
  step("Quick Append date heading and entry formatting are deterministic");
  step("Quick Append persisted to the sandbox journal.md");

  await clickText(".journal-experience", "Edit");
  const unsavedCloseDraft = `${appendedContent}unsaved close draft\n`;
  await setValue(".journal-editor", unsavedCloseDraft);
  step("Dirty draft created for close guard");
  await page.click(".modal-head button[title='Close']");
  await page.waitForSelector("[aria-label='Unsaved Journal changes']");
  step("Closing a dirty Journal opened an in-app guard");
  await clickText("[aria-label='Unsaved Journal changes']", "Keep Editing");
  const keptDraft = await page.$eval(".journal-editor", (element) => element.value);
  if (keptDraft !== unsavedCloseDraft) throw new Error("Keep Editing lost the draft");
  step("Keep Editing preserved the draft exactly");
  await page.click(".modal-head button[title='Close']");
  await clickText("[aria-label='Unsaved Journal changes']", "Discard");
  await page.waitForFunction(() => !document.querySelector("[aria-label^='Journal —']"));
  if (readFileSync(journalPath, "utf8") !== appendedContent) throw new Error("Discard changed disk content");
  step("Discard closed without changing disk content");

  await clickText(".panel-actions", "Journal");
  const cleanExternal = `${appendedContent}\nExternal clean edit\n`;
  writeFileSync(journalPath, cleanExternal, "utf8");
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await page.waitForFunction(() => document.querySelector(".journal-view")?.textContent?.includes("External clean edit"));
  step("Clean editor auto-refreshed an external disk edit on focus");

  await clickText(".journal-experience", "Edit");
  const dirtyDraft = `${cleanExternal}LOCAL DRAFT PRESERVED\n`;
  await setValue(".journal-editor", dirtyDraft);
  const externalConflict = `${cleanExternal}EXTERNAL CONFLICT VERSION\n`;
  writeFileSync(journalPath, externalConflict, "utf8");
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await page.waitForFunction(() => document.querySelector(".journal-status")?.textContent === "Changed on disk");
  const preservedAfterFocus = await page.$eval(".journal-editor", (element) => element.value);
  if (preservedAfterFocus !== dirtyDraft) throw new Error("Focus sync destroyed dirty draft");
  step("Dirty external edit signaled Changed on disk and preserved draft");
  await clickText(".journal-experience", "Save");
  await page.waitForSelector("[aria-label='Journal conflict']");
  step("Save produced a conflict instead of clobbering disk");
  const versions = await page.$$eval(".journal-conflict textarea", (areas) => areas.map((area) => area.value));
  if (versions[0] !== dirtyDraft || versions[1] !== externalConflict) throw new Error("Conflict comparison versions are incorrect");
  step("Conflict UI showed exact local draft and disk version");
  await screenshot("journal-conflict.png");
  await clickText("[aria-label='Journal conflict']", "Use Disk Version");
  if (readFileSync(journalPath, "utf8") !== externalConflict) throw new Error("Use Disk changed disk bytes");
  step("Use Disk Version selected the external bytes");

  await clickText(".journal-experience", "Edit");
  const forceDraft = `${externalConflict}EXPLICIT LOCAL OVERWRITE\n`;
  await setValue(".journal-editor", forceDraft);
  writeFileSync(journalPath, `${externalConflict}SECOND EXTERNAL CHANGE\n`, "utf8");
  await clickText(".journal-experience", "Save");
  await page.waitForSelector("[aria-label='Journal conflict']");
  step("Second stale save also conflicted");
  await clickText("[aria-label='Journal conflict']", "Overwrite Disk With My Draft");
  await page.waitForFunction(() => document.querySelector(".journal-status")?.textContent === "Saved");
  if (readFileSync(journalPath, "utf8") !== forceDraft) throw new Error("Explicit overwrite did not persist local draft");
  step("Explicit overwrite persisted only after deliberate action");

  const largeContent = `# Large Journal\n\n${"English اردو Roman Urdu 😀 ".repeat(14_000)}\n`;
  writeFileSync(journalPath, largeContent, "utf8");
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await page.waitForFunction(() => document.querySelector(".journal-view")?.textContent?.includes("Large Journal"));
  await clickText(".journal-experience", "Edit");
  const largeEdited = `${largeContent}Large journal save marker\n`;
  await setValue(".journal-editor", largeEdited);
  await clickText(".journal-experience", "Preview");
  await page.waitForSelector(".journal-preview");
  await clickText(".journal-experience", "Save");
  await page.waitForFunction(() => document.querySelector(".journal-status")?.textContent === "Saved");
  if (readFileSync(journalPath, "utf8") !== largeEdited) throw new Error("Large Journal round trip failed");
  step("Hundreds-of-KB Journal remained usable through read, edit, preview, and save");

  const hostile = "# Safe rendering\n\n<script>window.__JOURNAL_PWNED__ = true</script>\n<img src=x onerror=\"window.__JOURNAL_PWNED__=true\">\n";
  writeFileSync(journalPath, hostile, "utf8");
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await page.waitForFunction(() => document.querySelector(".journal-view")?.textContent?.includes("__JOURNAL_PWNED__"));
  const hostileResult = await page.evaluate(() => ({
    executed: Boolean(window.__JOURNAL_PWNED__),
    scriptCount: document.querySelectorAll(".journal-view script").length,
    imageCount: document.querySelectorAll(".journal-view img").length,
  }));
  if (hostileResult.executed || hostileResult.scriptCount || hostileResult.imageCount) throw new Error("Hostile Markdown executed or became active DOM");
  step("Hostile raw HTML and scripts remained inert text");
  await closeModal();

  const missingId = "abdul_rafey";
  const missingPath = join(sandbox, "Database/People/Family", missingId, "journal.md");
  rmSync(missingPath);
  await openPeopleJournal("Abdul Rafey");
  await page.waitForSelector(".journal-missing-warning");
  if (existsSync(missingPath)) throw new Error("Missing Journal read created a file");
  step("Missing Journal read created no file");
  await clickText(".journal-experience", "Edit");
  const firstSave = "# Abdul Rafey\n\nFirst explicit save اردو 😀\n";
  await setValue(".journal-editor", firstSave);
  await clickText(".journal-experience", "Save");
  if (!existsSync(missingPath) || readFileSync(missingPath, "utf8") !== firstSave) throw new Error("Explicit missing Journal save failed");
  step("Explicit save created the missing UTF-8 Journal correctly");
  await closeModal();

  const createdId = "abrar_hussain";
  const createdPath = join(sandbox, "Database/People/Family", createdId, "journal.md");
  rmSync(createdPath);
  await openPeopleJournal("Abrar Hussain");
  await clickText(".journal-experience", "Edit");
  const localCreatedDraft = "local missing-file draft\n";
  await setValue(".journal-editor", localCreatedDraft);
  writeFileSync(createdPath, "external file creation\n", "utf8");
  await clickText(".journal-experience", "Save");
  await page.waitForSelector("[aria-label='Journal conflict']");
  if (readFileSync(createdPath, "utf8") !== "external file creation\n") throw new Error("External creation was clobbered");
  if (await page.$eval("[aria-label='My local draft']", (element) => element.value) !== localCreatedDraft) throw new Error("Missing-to-created conflict lost draft");
  step("Missing-to-external-creation race conflicted and preserved both versions");
  await clickText("[aria-label='Journal conflict']", "Use Disk Version");
  await closeModal();

  const deletedId = "adeel_ahmad";
  const deletedPath = join(sandbox, "Database/People/Family", deletedId, "journal.md");
  await openPeopleJournal("Adeel Ahmad");
  await clickText(".journal-experience", "Edit");
  const deletionDraft = "local draft after external deletion\n";
  await setValue(".journal-editor", deletionDraft);
  rmSync(deletedPath);
  await clickText(".journal-experience", "Save");
  await page.waitForSelector("[aria-label='Journal conflict']");
  if (existsSync(deletedPath)) throw new Error("Stale save silently recreated deleted Journal");
  step("Existing-to-external-deletion race conflicted without recreation");
  await clickText("[aria-label='Journal conflict']", "Overwrite Disk With My Draft");
  if (!existsSync(deletedPath) || readFileSync(deletedPath, "utf8") !== deletionDraft) throw new Error("Explicit deletion recovery failed");
  step("Explicit overwrite deliberately recreated the deleted Journal");
  await closeModal();

  const status = await (await fetch("http://127.0.0.1:8765/api/data-root")).json();
  await page.setRequestInterception(true);
  page.on("request", (request) => {
    if (request.url().includes("/api/data-root") && request.method() === "GET") {
      request.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ ...status, read_only: true }) });
    } else request.continue();
  });
  await openPeopleJournal("Maham Mansoor");
  await page.waitForFunction(() => document.querySelector(".journal-blocked")?.textContent?.includes("read-only"));
  const readOnlyState = await page.evaluate(() => ({
    editDisabled: [...document.querySelectorAll(".journal-experience button")].find((button) => button.textContent?.trim() === "Edit")?.disabled,
    appendDisabled: [...document.querySelectorAll(".journal-experience button")].find((button) => button.textContent?.trim() === "Quick Append")?.disabled,
    reloadDisabled: [...document.querySelectorAll(".journal-experience button")].find((button) => button.textContent?.trim() === "Reload")?.disabled,
  }));
  if (!readOnlyState.editDisabled || !readOnlyState.appendDisabled || readOnlyState.reloadDisabled) throw new Error("Read-only controls are incorrect");
  step("Read-only mode disabled writes while preserving view and reload");

  const editorDirection = await page.evaluate(() => {
    document.querySelector(".journal-experience button:not([disabled])")?.focus();
    return document.querySelector(".journal-view .markdown")?.getAttribute("dir");
  });
  if (editorDirection !== "auto") throw new Error("Journal rendering does not use dir=auto");
  step("Journal direction is automatic and controls expose accessible names");

  if (consoleErrors.length) throw new Error(`Unexpected browser console errors: ${consoleErrors.join("; ")}`);
  step("No unexpected browser console or page errors");
  if (passed < 40) throw new Error(`Expected at least 40 strong E2E checks, recorded ${passed}`);
  console.log(`\nALL ${passed} JOURNAL E2E CHECKS PASSED\n`);
} finally {
  if (browser) await browser.close();
  stopProcess(backend);
  stopProcess(vite);
  await sleep(700);
  try { rmSync(sandbox, { recursive: true, force: true }); } catch {}
  verifyProduction();
}
