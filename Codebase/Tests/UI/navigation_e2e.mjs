import puppeteer from "puppeteer-core";
import { createHash } from "node:crypto";
import { execFileSync, spawn } from "node:child_process";
import {
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

function collectFiles(root) {
  if (!existsSync(root)) return [];
  const rows = [];
  function scan(dir) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name);
      if (entry.isDirectory()) scan(path);
      else rows.push({
        path: relative(root, path).replaceAll("\\", "/"),
        bytes: statSync(path).size,
        hash: sha256(path),
      });
    }
  }
  scan(root);
  return rows.sort((a, b) => a.path.localeCompare(b.path));
}

const production = {
  db: sha256(PROD_DB),
  journals: collectFiles(PROD_PEOPLE).filter((row) => row.path.endsWith("/journal.md")),
  backups: collectFiles(PROD_BACKUPS),
  bootstrap: existsSync(REAL_BOOTSTRAP)
    ? { exists: true, bytes: statSync(REAL_BOOTSTRAP).size, hash: sha256(REAL_BOOTSTRAP) }
    : { exists: false },
};

const sandbox = resolve(tmpdir(), `navigation_e2e_${Date.now()}`);
const bootstrap = join(sandbox, "settings", "bootstrap.json");
const rootA = join(sandbox, "Root A");
const rootB = join(sandbox, "Root B");
const missingRoot = join(sandbox, "Missing Root");
mkdirSync(dirname(bootstrap), { recursive: true });
mkdirSync(SHOTS, { recursive: true });

const python = process.platform === "win32" && existsSync(resolve(ROOT, ".venv/Scripts/python.exe"))
  ? resolve(ROOT, ".venv/Scripts/python.exe")
  : process.platform === "win32" ? "python" : "python3";
const env = { ...process.env };
delete env.PEOPLE_RELATIONSHIPS_ROOT;
Object.assign(env, {
  PYTHONUTF8: "1",
  PYTHONPATH: [resolve(ROOT, "App"), resolve(ROOT, "Scripts"), ROOT, process.env.PYTHONPATH]
    .filter(Boolean)
    .join(process.platform === "win32" ? ";" : ":"),
  PEOPLE_RELATIONSHIPS_BOOTSTRAP: bootstrap,
});

const backend = spawn(python, ["-m", "app.backend.main"], { cwd: ROOT, env, stdio: "pipe" });
const vite = spawn(process.platform === "win32" ? "npm.cmd" : "npm", ["--prefix", "App/Frontend", "run", "dev"], {
  cwd: ROOT,
  env,
  stdio: "pipe",
  shell: process.platform === "win32",
});
backend.stdout.on("data", () => undefined);
backend.stderr.on("data", (data) => { if (/Traceback|ERROR/.test(data.toString())) console.error(data.toString()); });
vite.stdout.on("data", () => undefined);
vite.stderr.on("data", (data) => console.error(data.toString()));

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
  if (process.platform === "win32") {
    try { execFileSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" }); } catch {}
  } else {
    try { child.kill("SIGKILL"); } catch {}
  }
}
function verifyProduction() {
  if (sha256(PROD_DB) !== production.db) throw new Error("Production database changed");
  if (JSON.stringify(collectFiles(PROD_PEOPLE).filter((row) => row.path.endsWith("/journal.md"))) !== JSON.stringify(production.journals)) throw new Error("Production Journals changed");
  if (JSON.stringify(collectFiles(PROD_BACKUPS)) !== JSON.stringify(production.backups)) throw new Error("Production Backups changed");
  const now = existsSync(REAL_BOOTSTRAP)
    ? { exists: true, bytes: statSync(REAL_BOOTSTRAP).size, hash: sha256(REAL_BOOTSTRAP) }
    : { exists: false };
  if (JSON.stringify(now) !== JSON.stringify(production.bootstrap)) throw new Error("Real bootstrap changed");
}

let browser;
let page;
let backendStopped = false;
let passed = 0;
const consoleErrors = [];
function step(label) { passed += 1; console.log(`✓ [Navigation E2E ${passed}] ${label}`); }
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
async function clickArticleButton(name, label) {
  await page.waitForFunction((expectedName, expectedLabel) => [...document.querySelectorAll(".search-result")].some((article) =>
    article.textContent?.includes(expectedName) && [...article.querySelectorAll("button")].some((button) => button.textContent?.includes(expectedLabel))),
  { timeout: 20_000 }, name, label);
  await page.evaluate((expectedName, expectedLabel) => {
    const article = [...document.querySelectorAll(".search-result")].find((item) => item.textContent?.includes(expectedName));
    [...(article?.querySelectorAll("button") ?? [])].find((button) => button.textContent?.includes(expectedLabel))?.click();
  }, name, label);
}
async function setValue(selector, value) {
  await page.waitForSelector(selector, { visible: true, timeout: 20_000 });
  await page.$eval(selector, (element, next) => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(element, next);
    element.dispatchEvent(new Event("input", { bubbles: true }));
  }, value);
}
async function search(selector, value) {
  await page.waitForSelector(selector, { visible: true, timeout: 20_000 });
  await page.click(selector);
  await page.keyboard.down("Control");
  await page.keyboard.press("KeyA");
  await page.keyboard.up("Control");
  await page.keyboard.press("Backspace");
  await page.type(selector, value);
}
async function screenshot(name) {
  await sleep(300);
  await page.screenshot({ path: join(SHOTS, name) });
}
async function nav(label) {
  await clickText(".nav", label);
  await page.waitForFunction((expected) => {
    const active = document.querySelectorAll(".nav-item[aria-current='page']");
    return active.length === 1 && active[0].textContent?.includes(expected);
  }, { timeout: 20_000 }, label);
}

try {
  if (production.db !== "3258C738F9D65B23B15970D0E1E7389E8584A35BA8E26030249061BAF74E096E") throw new Error("Unexpected production DB baseline");
  if (production.journals.length !== 35 || production.backups.length !== 176) throw new Error("Unexpected production inventory baseline");
  await waitForUrl("http://127.0.0.1:8765/api/health");
  await waitForUrl("http://localhost:1420");
  browser = await puppeteer.launch({ executablePath: EDGE, headless: "new", args: ["--disable-gpu", "--no-first-run", "--no-sandbox", "--edge-skip-compat-layer-relaunch"], defaultViewport: { width: 1500, height: 1000 } });
  page = await browser.newPage();
  page.on("console", (message) => {
    if (message.type() === "error" && !message.text().includes("Failed to load resource")) consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(`pageerror: ${error.message}`));
  await page.evaluateOnNewDocument(() => {
    window.__forbiddenDialogs = 0;
    window.prompt = window.alert = window.confirm = () => { window.__forbiddenDialogs += 1; return false; };
  });
  await page.goto("http://localhost:1420", { waitUntil: "networkidle0", timeout: 40_000 });
  await page.waitForFunction(() => document.body.textContent?.includes("Welcome to People Relationships"));
  step("Unconfigured onboarding remains distinct from backend failure");

  await clickText("main", "Create New Data Root");
  await setValue("#new-root-path", rootA);
  await setValue("#owner-name", "Alice Root A");
  await clickText("main", "Review New Data Root");
  await clickText("main", "Confirm Create New Data Root");
  await page.waitForFunction(() => document.querySelector("[role='status']")?.textContent?.includes("ready"), { timeout: 30_000 });
  await clickText("main", "Continue");
  await page.waitForSelector(".nav", { timeout: 30_000 });
  step("Successful first-run recovery enters the normal shell only after completion");

  const amina = (await post("/api/people", { name: "Amina Root A", gender: "female", group_ids: ["family"] })).person;
  const farah = (await post("/api/people", { name: "Farah Root A", gender: "female", group_ids: ["family"] })).person;
  await post("/api/relationships/general", { person_a: "alice_root_a", person_b: amina.id, type: "close_friend", directionality: "symmetric" });
  await post("/api/relationships/general", { person_a: amina.id, person_b: farah.id, type: "close_friend", directionality: "symmetric" });

  await post("/api/data-root/initialize", { target_path: rootB, owner_name: "Bob Root B", owner_gender: "male" });
  const bilal = (await post("/api/people", { name: "Bilal Root B", gender: "male", group_ids: ["family"] })).person;
  const zoya = (await post("/api/people", { name: "Zoya Root B", gender: "female", group_ids: ["family"] })).person;
  await post("/api/relationships/general", { person_a: bilal.id, person_b: zoya.id, type: "close_friend", directionality: "symmetric" });
  await post("/api/data-root/switch", { target_path: rootA });
  await page.reload({ waitUntil: "networkidle0", timeout: 40_000 });
  await page.waitForFunction(() => document.body.textContent?.includes("Alice Root A"));

  const pureDb = sha256(join(rootA, "Database/Main/family.db"));
  const pureJournals = collectFiles(join(rootA, "Database/People")).filter((row) => row.path.endsWith("/journal.md"));
  const pureBackups = collectFiles(join(rootA, "Backups"));
  for (const label of ["People", "Relationships", "Family", "Search", "Hermes", "Backups"]) await nav(label);
  await nav("People");
  if ((await page.$$eval(".nav-item[aria-current='page']", (items) => items.length)) !== 1) throw new Error("Primary navigation has multiple active destinations");
  if (sha256(join(rootA, "Database/Main/family.db")) !== pureDb || JSON.stringify(collectFiles(join(rootA, "Database/People")).filter((row) => row.path.endsWith("/journal.md"))) !== JSON.stringify(pureJournals) || JSON.stringify(collectFiles(join(rootA, "Backups"))) !== JSON.stringify(pureBackups)) throw new Error("Primary navigation caused a data write");
  step("All six primary destinations have one truthful active state; repeated navigation is stable and read-side pure");
  await screenshot("primary-navigation-people.png");

  await page.waitForFunction(() => [...document.querySelectorAll(".people-table-row")].some((row) => row.textContent?.includes("Amina Root A")));
  await page.evaluate(() => [...document.querySelectorAll(".people-table-row")].find((row) => row.textContent?.includes("Amina Root A"))?.querySelector(".person-cell")?.click());
  await page.waitForFunction(() => document.querySelector(".modal")?.textContent?.includes("Amina Root A"));
  step("People opens the canonical profile target");
  await clickText(".modal", "Show Relationship Path");
  await page.waitForFunction(() => document.querySelector(".selected-person-panel")?.textContent?.includes("Amina Root A"), { timeout: 20_000 });
  step("Profile to Relationships targets the same canonical person");
  await clickText(".navigation-return", "Return to People");
  await page.waitForFunction(() => document.querySelector(".modal")?.textContent?.includes("Amina Root A"));
  await clickText(".modal", "View Family");
  await page.waitForFunction(() => document.querySelector(".family-side")?.textContent?.includes("Amina Root A"));
  await clickText(".navigation-return", "Return to People");
  await page.waitForFunction(() => document.querySelector(".modal")?.textContent?.includes("Amina Root A"));
  step("Return restores the originating People profile context across Relationships and Family");
  await page.click(".modal-head button[title='Close']");

  await nav("Relationships");
  await nav("People");
  if (await page.$(".modal")) throw new Error("Primary People navigation reopened a stale contextual profile");
  await nav("Relationships");
  await search(".relationships-search-wrap input", "Farah Root A");
  await page.waitForSelector(".person-search-row", { visible: true });
  await page.click(".person-search-row");
  await page.waitForFunction(() => document.querySelector(".selected-person-panel")?.textContent?.includes("Farah Root A"));
  await clickText(".selected-person-panel", "View Profile");
  await page.waitForFunction(() => document.querySelector(".modal")?.textContent?.includes("Farah Root A"));
  await clickText(".modal", "Return to Relationships");
  await page.waitForFunction(() => document.querySelector(".selected-person-panel")?.textContent?.includes("Farah Root A"));
  await clickText(".selected-person-panel", "View Family");
  await page.waitForFunction(() => document.querySelector(".family-side")?.textContent?.includes("Farah Root A"));
  await clickText(".navigation-return", "Return to Relationships");
  await page.waitForFunction(() => document.querySelector(".selected-person-panel")?.textContent?.includes("Farah Root A"));
  step("Relationships to Profile/Family and return preserves the exact target without stale People state");

  await nav("Family");
  await search(".family-focus-search-wrap input", "Amina Root A");
  await page.waitForSelector(".family-focus-search-wrap .person-search-row", { visible: true });
  await page.click(".family-focus-search-wrap .person-search-row");
  await page.waitForFunction(() => document.querySelector(".family-focus-current")?.textContent?.includes("Amina Root A"), { timeout: 20_000 });
  const globalBeforeFamilyHandoff = await page.$eval(".perspective-current", (node) => node.textContent);
  if (!globalBeforeFamilyHandoff.includes("Alice Root A")) throw new Error("Family focus changed global My Perspective");
  step("Family focus is independent from global My Perspective");
  await page.waitForSelector(".family-diagram svg", { timeout: 20_000 });
  const clickedFarah = await page.evaluate(() => {
    const node = document.querySelector('g.node[id*="p_farah_root_a"]');
    node?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    return Boolean(node);
  });
  if (!clickedFarah) throw new Error("Farah canonical Family node not found");
  await page.waitForFunction(() => document.querySelector(".family-side")?.textContent?.includes("Farah Root A"));
  await clickText(".family-side", "View in Relationships");
  await page.waitForFunction(() => document.querySelector(".relationships-head")?.textContent?.includes("Amina Root A") && document.querySelector(".selected-person-panel")?.textContent?.includes("Farah Root A"), { timeout: 20_000 });
  step("Family to Relationships awaits the exact Amina-to-Farah handoff");
  await screenshot("navigation-family-to-relationships.png");
  await clickText(".navigation-return", "Return to Family");
  await page.waitForFunction(() => document.querySelector(".family-focus-current")?.textContent?.includes("Amina Root A") && document.querySelector(".family-side")?.textContent?.includes("Farah Root A"));
  step("Return to Family preserves focus and selected-person context");

  await nav("Search");
  await search(".search-bar input", "Farah Root A");
  await clickText(".search-bar", "Search");
  await clickArticleButton("Farah Root A", "Details");
  await page.waitForFunction(() => document.querySelector(".modal")?.textContent?.includes("Farah Root A"));
  await screenshot("navigation-search-to-profile.png");
  await clickText(".modal", "Return to Search");
  if ((await page.$eval(".search-bar input", (input) => input.value)) !== "Farah Root A") throw new Error("Search query was not preserved");
  await page.waitForFunction(() => document.querySelector(".search-results-list")?.textContent?.includes("Farah Root A"));
  await clickArticleButton("Farah Root A", "View Family");
  await page.waitForFunction(() => document.querySelector(".family-side")?.textContent?.includes("Farah Root A"));
  await clickText(".navigation-return", "Return to Search");
  if ((await page.$eval(".search-bar input", (input) => input.value)) !== "Farah Root A") throw new Error("Search query was not preserved after Family");
  step("Search to Profile/Family and return preserves the legitimate query/results context");

  await search(".search-bar input", "Root A");
  await clickText(".search-bar", "Search");
  await page.waitForFunction(() => document.querySelectorAll(".search-result").length >= 3);
  await page.evaluate(() => {
    const articles = [...document.querySelectorAll(".search-result")];
    for (const name of ["Amina Root A", "Farah Root A"]) {
      const article = articles.find((item) => item.textContent?.includes(name));
      [...(article?.querySelectorAll("button") ?? [])].find((button) => button.textContent?.includes("View in Relationships"))?.click();
    }
  });
  await page.waitForFunction(() => document.querySelector(".selected-person-panel")?.textContent?.includes("Farah Root A"), { timeout: 20_000 });
  step("Rapid contextual handoffs deterministically select the last canonical target");
  await clickText(".navigation-return", "Return to Search");

  await nav("Backups");
  await page.waitForSelector(".data-root-panel", { timeout: 20_000 });
  await screenshot("navigation-backups.png");
  if (JSON.stringify(collectFiles(join(rootA, "Backups"))) !== JSON.stringify(pureBackups)) throw new Error("Opening Backups created or changed a backup");
  step("Backups is a normal primary screen and navigation creates no backup");
  await clickText(".data-root-panel", "Change Location");
  await clickText("[aria-label='Change Data Location']", "Use Existing Data Root");
  await setValue("#change-root-path", rootB);
  await clickText("[aria-label='Change Data Location']", "Inspect Data Root");
  await clickText("[aria-label='Change Data Location']", "Confirm Use This Data Root");
  await page.waitForFunction(() => document.querySelector("[role='status']")?.textContent?.includes("now active"), { timeout: 30_000 });
  await clickText("[aria-label='Change Data Location']", "Reload and Continue");
  await page.waitForFunction(() => document.body.textContent?.includes("Bob Root B"), { timeout: 30_000 });
  if ((await page.$eval("body", (node) => node.textContent)).includes("Alice Root A")) throw new Error("Root A identity leaked after switching to Root B");
  await nav("Search");
  if ((await page.$eval(".search-bar input", (input) => input.value)) !== "") throw new Error("Root A Search query survived root switch");
  await nav("Family");
  await page.waitForFunction(() => document.querySelector(".family-focus-current")?.textContent?.includes("Bob Root B"), { timeout: 20_000 });
  step("Root switch remounts all root-bound navigation state around Root B");

  writeFileSync(bootstrap, JSON.stringify({ active_root: missingRoot, updated_at: "2026-09-10T00:00:00Z" }), "utf8");
  await page.reload({ waitUntil: "networkidle0", timeout: 40_000 });
  await page.waitForFunction(() => document.body.textContent?.includes("Data location unavailable"));
  if ((await page.$eval("body", (node) => node.textContent)).includes("Welcome to People Relationships")) throw new Error("Missing root collapsed into onboarding");
  step("Missing-root recovery remains distinct from onboarding");
  await clickText("main", "Use Existing Data Root");
  await setValue("#existing-root-path", rootB);
  await clickText("main", "Inspect Data Root");
  await clickText("main", "Confirm Use This Data Root");
  await page.waitForFunction(() => document.querySelector("[role='status']")?.textContent?.includes("active"), { timeout: 30_000 });
  await clickText("main", "Continue");
  await page.waitForFunction(() => document.body.textContent?.includes("Bob Root B"), { timeout: 30_000 });
  step("Successful recovery returns to a fresh normal shell");

  stop(backend);
  backendStopped = true;
  await page.reload({ waitUntil: "domcontentloaded", timeout: 40_000 });
  await page.waitForFunction(() => document.body.textContent?.includes("Data Service Unavailable"), { timeout: 20_000 });
  step("Backend failure remains a distinct StartupFailure state");

  const forbiddenDialogs = await page.evaluate(() => window.__forbiddenDialogs);
  if (forbiddenDialogs !== 0) throw new Error(`Browser dialogs called: ${forbiddenDialogs}`);
  if (consoleErrors.length) throw new Error(`Unexpected browser errors: ${consoleErrors.join(" | ")}`);
  step("Journey has no browser dialogs or unexpected console errors");
  verifyProduction();
  console.log(`\nALL ${passed} NAVIGATION / OVERALL UX E2E CHECKS PASSED\n`);
} finally {
  if (browser) await browser.close();
  if (!backendStopped) stop(backend);
  stop(vite);
  rmSync(sandbox, { recursive: true, force: true });
  verifyProduction();
}
