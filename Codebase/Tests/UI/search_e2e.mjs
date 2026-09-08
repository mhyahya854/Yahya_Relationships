import puppeteer from "puppeteer-core";
import {
  chmodSync,
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { createHash } from "node:crypto";
import { execFileSync, spawn } from "node:child_process";
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
const DEFAULT_PERSON_ID = "mohammad_yahya_hussain";
const DEFAULT_PERSON_NAME = "Mohammad Yahya Hussain";

function sha256(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex").toUpperCase();
}

function collectFiles(root) {
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

function collectJournals(root) {
  return collectFiles(root).filter((row) => row.path.endsWith("/journal.md"));
}

function sameManifest(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

const productionDbHash = sha256(PROD_DB);
const productionJournals = collectJournals(PROD_PEOPLE);
if (productionJournals.length !== 35) {
  throw new Error(`Expected 35 production journals, found ${productionJournals.length}`);
}
console.log(`[Safety Baseline] Production DB ${productionDbHash}; journals ${productionJournals.length}`);

const sandbox = resolve(tmpdir(), `search_e2e_root_${Date.now()}`);
mkdirSync(sandbox, { recursive: true });
cpSync(resolve(REPO_ROOT, "Database"), join(sandbox, "Database"), { recursive: true });
mkdirSync(SCREENSHOTS, { recursive: true });

const journalPath = join(sandbox, "Database/People/Family", DEFAULT_PERSON_ID, "journal.md");
const originalJournal = readFileSync(journalPath, "utf8");
const searchJournal = `${originalJournal.trimEnd()}\n\n## Phase 6 Search Fixture\n\n` +
  "English: cobalt compass search phrase.\n\n" +
  "Urdu: نیلا قطب نما تلاش عبارت۔\n\n" +
  "Roman Urdu: neela qutub numa talash jumla.\n\n" +
  "Literal tokens: percent%token and underscore_token.\n\n" +
  "<script>window.__searchPwned=1</script>\n\n" +
  "<img src=x onerror=\"window.__searchPwned=1\">\n";
writeFileSync(journalPath, searchJournal, "utf8");

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

const sleep = (ms) => new Promise((resolveSleep) => setTimeout(resolveSleep, ms));
async function waitForUrl(url, timeout = 30_000) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {}
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

function stopProcess(child) {
  if (!child?.pid) return;
  if (process.platform === "win32") {
    try { execFileSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" }); } catch {}
  } else {
    try { child.kill("SIGKILL"); } catch {}
  }
}

function verifyProduction() {
  if (sha256(PROD_DB) !== productionDbHash) throw new Error("Production database hash changed");
  const current = collectJournals(PROD_PEOPLE);
  if (!sameManifest(current, productionJournals)) throw new Error("A production Journal changed");
  console.log("[Safety Verification] Database and all 35 production journals are byte-identical.");
}

let browser;
let page;
let passed = 0;
function step(label) {
  passed += 1;
  console.log(`✓ [Search E2E ${passed}] ${label}`);
}

async function clickText(scope, text) {
  await page.waitForFunction((selector, expected) => {
    return [...document.querySelectorAll(`${selector} button`)].some((button) => {
      const rect = button.getBoundingClientRect();
      return button.textContent?.trim().includes(expected) && !button.disabled && rect.width > 0 && rect.height > 0;
    });
  }, { timeout: 15_000 }, scope, text);
  await page.evaluate((selector, expected) => {
    const button = [...document.querySelectorAll(`${selector} button`)].find(
      (candidate) => candidate.textContent?.trim().includes(expected) && !candidate.disabled,
    );
    button.click();
  }, scope, text);
}

async function navigate(label) {
  await clickText(".nav", label);
  await page.waitForFunction((expected) => document.querySelector(".nav-item.active")?.textContent?.includes(expected), {}, label);
}

async function setValue(selector, value) {
  await page.waitForSelector(selector, { visible: true, timeout: 15_000 });
  await page.$eval(selector, (element, nextValue) => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(element, nextValue);
    element.dispatchEvent(new Event("input", { bubbles: true }));
  }, value);
}

async function submitSearch(term) {
  await setValue("input[aria-label='Global search']", term);
  await page.$eval("form[role='search']", (form) => {
    form.dispatchEvent(new SubmitEvent("submit", { bubbles: true, cancelable: true }));
  });
  await page.waitForFunction(() => {
    const list = document.querySelector(".search-results-list");
    return list?.getAttribute("aria-busy") === "false" &&
      (document.querySelectorAll(".search-result").length > 0 || Boolean(document.querySelector(".empty-state")));
  }, { timeout: 20_000 });
}

async function searchResults() {
  return page.$$eval(".search-result", (nodes) => nodes.map((node) => ({
    id: node.getAttribute("data-result-id"),
    text: node.textContent,
    category: node.querySelector(".tag")?.textContent,
  })));
}

async function screenshot(name) {
  await page.screenshot({ path: join(SCREENSHOTS, name) });
}

try {
  await waitForUrl("http://127.0.0.1:8765/api/health");
  await waitForUrl("http://localhost:1420");

  await api("/api/state", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ perspective_person_id: DEFAULT_PERSON_ID }),
  });
  const seededGeneral = await api("/api/relationships/general", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      person_a: DEFAULT_PERSON_ID,
      person_b: "sohaib_hussain",
      type: "custom",
      directionality: "directional",
      label_a_to_b: "Phase Six trusted mentor with a deliberately long searchable orientation label",
      label_b_to_a: "Phase Six supported mentee",
      notes: "Cobalt directional orientation note · اردو سمت",
    }),
  });
  const generalId = seededGeneral.relationship.id;

  browser = await puppeteer.launch({
    executablePath: EDGE,
    headless: "new",
    args: ["--disable-gpu", "--no-first-run", "--no-sandbox", "--edge-skip-compat-layer-relaunch"],
    defaultViewport: { width: 1600, height: 1000 },
  });
  page = await browser.newPage();
  const consoleErrors = [];
  const responseErrors = [];
  page.on("console", (message) => {
    const text = message.text();
    if (message.type() === "error" && !text.includes("Failed to load resource")) consoleErrors.push(text);
  });
  page.on("response", (response) => {
    if (response.status() >= 400 && !response.url().endsWith("/favicon.ico")) {
      responseErrors.push(`${response.status()} ${response.url()}`);
    }
  });
  page.on("pageerror", (error) => consoleErrors.push(`pageerror: ${error.message}`));

  await page.goto("http://localhost:1420", { waitUntil: "networkidle0", timeout: 40_000 });
  await page.waitForSelector(".perspective-current", { timeout: 15_000 });
  await navigate("Search");
  await page.waitForSelector(".search-view");
  step("Search screen opens");

  const inputAccess = await page.$eval("input[aria-label='Global search']", (input) => ({
    focused: document.activeElement === input,
    formRole: input.closest("form")?.getAttribute("role"),
  }));
  if (!inputAccess.focused || inputAccess.formRole !== "search") throw new Error("Search input autofocus/accessibility failed");
  step("Search input is labelled, focused, and inside search semantics");
  if (!(await page.$eval(".search-initial", (node) => node.textContent)).includes("Enter a query")) throw new Error("Initial empty state missing");
  step("Initial empty state is explicit");

  await submitSearch(DEFAULT_PERSON_NAME);
  let results = await searchResults();
  if (!results.some((row) => row.id === `person:${DEFAULT_PERSON_ID}`)) throw new Error("Exact canonical person result missing");
  step("Canonical person exact search resolves correctly");
  if (results.filter((row) => row.id === `person:${DEFAULT_PERSON_ID}`).length !== 1 || new Set(results.map((row) => row.id)).size !== results.length) {
    throw new Error("Person result duplicated or result IDs are unstable");
  }
  step("Person result has one stable ID and no duplicate");
  await screenshot("search-people.png");

  await submitSearch("Maaz");
  results = await searchResults();
  const aliasResult = results.find((row) => row.id === "person:muaaz");
  if (!aliasResult) throw new Error("Alias did not resolve canonical Muaaz person");
  step("Alias search finds the canonical person");
  if (!aliasResult.text.includes("Alias: Maaz")) throw new Error("Matched alias explanation missing");
  step("Matched alias is visibly explained");

  await clickText("[data-result-id='person:muaaz']", "Details");
  await page.waitForFunction(() => document.querySelector(".person-profile-container")?.textContent?.includes("Muaaz"));
  step("Person Details opens the exact canonical profile");
  if (!(await page.$eval(".perspective-current", (node) => node.textContent)).includes(DEFAULT_PERSON_NAME)) throw new Error("Details silently changed perspective");
  step("Opening Details preserves the current perspective");
  await page.click(".modal-head button[title='Close']");
  await navigate("Search");
  await submitSearch("Maaz");
  await clickText("[data-result-id='person:muaaz']", "View in Relationships");
  await page.waitForFunction(() => document.querySelector(".selected-person-panel")?.textContent?.includes("Muaaz"), { timeout: 20_000 });
  step("Person handoff selects the exact Relationships target");
  const personHandoff = await page.evaluate(() => ({
    perspective: document.querySelector(".perspective-current")?.textContent,
    panel: document.querySelector(".selected-person-panel")?.textContent,
  }));
  if (!personHandoff.perspective.includes(DEFAULT_PERSON_NAME) || !personHandoff.panel.includes(`Relationship to ${DEFAULT_PERSON_NAME}`)) {
    throw new Error("Person handoff silently changed perspective");
  }
  step("Person handoff preserves perspective A");
  await navigate("Search");
  step("Navigation returns to a usable Search screen");

  await submitSearch("Family");
  results = await searchResults();
  const familyGroup = results.find((row) => row.id === "group:family");
  if (!familyGroup || !familyGroup.text.includes("35 members")) throw new Error("Canonical Family group result missing");
  step("Group search returns a stable canonical group result");
  await screenshot("search-group.png");
  await clickText("[data-result-id='group:family']", "View members");
  await page.waitForFunction(() => document.querySelector(".tabs .tab.active")?.textContent?.includes("Family (35)"));
  const groupRows = await page.$$eval(".people-table-row", (nodes) => nodes.length);
  if (groupRows !== 35) throw new Error(`Family group showed ${groupRows} rows, expected 35`);
  step("Group handoff shows all 35 actual canonical members");
  const muaazCount = await page.$$eval(".person-cell", (nodes) => nodes.filter((node) => node.textContent?.includes("Muaaz")).length);
  if (muaazCount !== 1) throw new Error("Group view duplicated or omitted canonical Muaaz");
  await page.evaluate(() => {
    const cell = [...document.querySelectorAll(".person-cell")].find((node) => node.textContent?.includes("Muaaz"));
    cell?.click();
  });
  await page.waitForFunction(() => document.querySelector(".person-profile-container")?.textContent?.includes("Muaaz"));
  step("A group member opens the correct profile without a pseudo-person duplicate");
  await page.click(".modal-head button[title='Close']");
  await navigate("Search");

  await submitSearch("Cobalt directional orientation");
  results = await searchResults();
  const generalResult = results.find((row) => row.id === `general:${generalId}`);
  if (!generalResult) throw new Error("Directional general relationship result missing");
  step("General relationship prose search resolves the stored relationship");
  if (!generalResult.text.includes("trusted mentor") || !generalResult.text.includes("supported mentee") || !generalResult.text.includes("اردو سمت")) {
    throw new Error("Directional labels or notes missing from Search result");
  }
  step("Both directional labels and notes are visibly oriented");
  await screenshot("search-relationship.png");
  await submitSearch("Phase Six supported mentee");
  await clickText(`[data-result-id='general:${generalId}']`, `View Sohaib Hussain → ${DEFAULT_PERSON_NAME}`);
  await page.waitForFunction((name) => document.querySelector(".selected-person-panel")?.textContent?.includes(name), { timeout: 20_000 }, DEFAULT_PERSON_NAME);
  step("General relationship handoff selects the exact endpoint");
  await page.waitForFunction(
    () => document.querySelector(".selected-person-panel")?.textContent?.includes("supported mentee"),
    { timeout: 20_000 },
  );
  const orientation = await page.evaluate(() => ({
    perspective: document.querySelector(".perspective-current")?.textContent,
    panel: document.querySelector(".selected-person-panel")?.textContent,
  }));
  if (!orientation.perspective.includes("Sohaib Hussain") || !orientation.panel.includes("supported mentee")) {
    throw new Error("Canonical general relationship orientation was not preserved");
  }
  step("General relationship handoff preserves canonical stored direction");
  await page.click(".topbar .btn.btn-ghost");
  await page.waitForFunction((name) => document.querySelector(".perspective-current")?.textContent?.includes(name), {}, DEFAULT_PERSON_NAME);

  await navigate("Search");
  await submitSearch("maternal uncle");
  results = await searchResults();
  const uncle = results.find((row) => row.id?.startsWith(`family:${DEFAULT_PERSON_ID}:sohaib_hussain:`));
  if (!uncle || !uncle.text.includes("Maternal uncle")) throw new Error("English family result missing");
  step("English family relationship term resolves deterministically");
  if (!uncle.text.includes(`from ${DEFAULT_PERSON_NAME}`)) throw new Error("Family result omits current perspective");
  step("Family result explicitly corresponds to the current perspective");
  await clickText(`[data-result-id='${uncle.id}']`, "View in Relationships");
  await page.waitForFunction(() => {
    const panel = document.querySelector(".selected-person-panel")?.textContent || "";
    return panel.includes("Sohaib Hussain") && panel.includes("Maternal uncle");
  }, { timeout: 20_000 });
  step("Family handoff preserves perspective, exact target, and displayed relationship");
  await navigate("Search");
  if (!(await page.$eval(".perspective-current", (node) => node.textContent)).includes(DEFAULT_PERSON_NAME)) throw new Error("Family Search altered perspective");
  step("Returning from family handoff confirms Search did not alter perspective A");

  await submitSearch("ماموں");
  results = await searchResults();
  if (!results.some((row) => row.id?.startsWith(`family:${DEFAULT_PERSON_ID}:sohaib_hussain:`))) throw new Error("Urdu family result missing");
  step("Urdu family relationship term resolves the same canonical target");
  if (!results.some((row) => row.text.includes("ماموں"))) throw new Error("Urdu result text is not visible");
  step("Urdu result text remains readable");

  await submitSearch("second cousin");
  const firstMultipath = (await searchResults()).filter((row) => row.id?.includes(":maham_mansoor:"));
  await submitSearch("second cousin");
  const secondMultipath = (await searchResults()).filter((row) => row.id?.includes(":maham_mansoor:"));
  if (firstMultipath.length < 2 || new Set(firstMultipath.map((row) => row.id)).size !== firstMultipath.length ||
      JSON.stringify(firstMultipath.map((row) => row.id)) !== JSON.stringify(secondMultipath.map((row) => row.id))) {
    throw new Error("Multipath family results are missing, collapsed, duplicated, or unstable");
  }
  step("Multipath family results retain distinct stable path IDs in deterministic order");

  await submitSearch("father");
  await page.waitForFunction((prefix) => [...document.querySelectorAll(".search-result")].some((node) => node.getAttribute("data-result-id")?.startsWith(prefix)), {}, `family:${DEFAULT_PERSON_ID}:mansoor_hussain:`);
  await page.click(".perspective-current");
  await clickText(".perspective-dropdown", "Irsa Naz");
  await page.waitForFunction(() => document.querySelector(".perspective-current")?.textContent?.includes("Irsa Naz"));
  step("The explicit perspective selector changes perspective");
  await page.waitForFunction(() => {
    const nodes = [...document.querySelectorAll(".search-result")];
    return nodes.some((node) => node.getAttribute("data-result-id")?.startsWith("family:irsa_naz:israr_hussain:"));
  }, { timeout: 20_000 });
  if ([...await page.$$eval(".search-result", (nodes) => nodes.map((node) => node.getAttribute("data-result-id")))].some((id) => id?.startsWith(`family:${DEFAULT_PERSON_ID}:`))) {
    throw new Error("Old-perspective family results survived recomputation");
  }
  step("The same query automatically recomputes for the new perspective");

  await page.click(".btn.btn-ghost");
  await page.waitForFunction((name) => document.querySelector(".perspective-current")?.textContent?.includes(name), {}, DEFAULT_PERSON_NAME);

  const journalQueries = [
    ["cobalt compass search phrase", "English"],
    ["نیلا قطب نما تلاش عبارت", "Urdu"],
    ["neela qutub numa talash jumla", "Roman Urdu"],
  ];
  for (const [term, language] of journalQueries) {
    await submitSearch(term);
    const journalResults = await searchResults();
    if (!journalResults.some((row) => row.id === `journal:${DEFAULT_PERSON_ID}`)) throw new Error(`${language} Journal query failed`);
  }
  step("English, Urdu, and Roman Urdu Journal phrases resolve the same canonical Journal");
  results = await searchResults();
  if (!results.find((row) => row.id === `journal:${DEFAULT_PERSON_ID}`)?.text.includes("neela qutub numa")) throw new Error("Journal snippet missing matched prose");
  step("Journal result includes a deterministic matching snippet");
  await screenshot("search-journal.png");
  await clickText(`[data-result-id='journal:${DEFAULT_PERSON_ID}']`, "Open Journal");
  await page.waitForSelector(".journal-experience", { timeout: 15_000 });
  await clickText(".journal-experience", "Edit");
  const modalJournal = await page.$eval(".journal-editor", (node) => node.value);
  if (modalJournal !== searchJournal) throw new Error("Shared Journal modal did not load exact canonical sandbox content");
  step("Open Journal uses the shared Journal UI and loads exact canonical content");
  await page.click(".modal-head button[title='Close']");

  await submitSearch("Maaz");
  await clickText(".search-filters", "People");
  if (!(await page.$eval(".search-filters button[aria-pressed='true']", (node) => node.textContent)).includes("People") ||
      (await searchResults()).some((row) => !row.id?.startsWith("person:"))) throw new Error("People filter failed");
  step("People category filter exposes selected state and only people");
  await submitSearch("maternal uncle");
  await clickText(".search-filters", "Relationships");
  if ((await searchResults()).some((row) => !row.id?.startsWith("family:") && !row.id?.startsWith("general:"))) throw new Error("Relationships filter failed");
  step("Relationships category filter is keyboard-button based and exact");
  await submitSearch("Family");
  await clickText(".search-filters", "Groups");
  if ((await searchResults()).some((row) => !row.id?.startsWith("group:"))) throw new Error("Groups filter failed");
  step("Groups category filter exposes only groups");
  await submitSearch("cobalt compass search phrase");
  await clickText(".search-filters", "Journals");
  if ((await searchResults()).some((row) => !row.id?.startsWith("journal:"))) throw new Error("Journals filter failed");
  step("Journals category filter exposes only Journals");

  await submitSearch("definitely-no-search-result-8f4c2d");
  const noResultsText = await page.$eval(".empty-state", (node) => node.textContent);
  if (!noResultsText.includes("No ") || !noResultsText.includes("results")) throw new Error("No-results state missing");
  step("No-results state is explicit");
  await submitSearch("%");
  if (!(await searchResults()).some((row) => row.id === `journal:${DEFAULT_PERSON_ID}`)) throw new Error("Literal percent was treated as a wildcard");
  step("Percent is treated as a literal search character");
  await submitSearch("_");
  if (!(await searchResults()).some((row) => row.id === `journal:${DEFAULT_PERSON_ID}`)) throw new Error("Literal underscore was treated as a wildcard");
  step("Underscore is treated as a literal search character");
  await clickText(".search-filters", "All");

  await page.evaluate(() => {
    window.__searchRealFetch = window.fetch;
    window.fetch = (input, init = {}) => {
      const url = new URL(String(input), window.location.href);
      if (!url.pathname.endsWith("/api/search")) return window.__searchRealFetch(input, init);
      const term = url.searchParams.get("q");
      const slow = term === "slowfirst";
      const payload = {
        query: term,
        normalized_query: term,
        perspective: { id: "mohammad_yahya_hussain", name: "Mohammad Yahya Hussain" },
        results: [{
          result_id: `person:${slow ? "muaaz" : "irsa_naz"}`,
          category: "PERSON",
          person_id: slow ? "muaaz" : "irsa_naz",
          title: slow ? "Slow Result" : "Fast Result",
          subtitle: "Person",
          match: "Canonical name",
        }],
      };
      return new Promise((resolve, reject) => {
        const timer = setTimeout(() => resolve(new Response(JSON.stringify(payload), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })), slow ? 700 : 40);
        init.signal?.addEventListener("abort", () => {
          clearTimeout(timer);
          reject(new DOMException("Aborted", "AbortError"));
        }, { once: true });
      });
    };
  });
  await setValue("input[aria-label='Global search']", "slowfirst");
  await page.$eval("form[role='search']", (form) => form.dispatchEvent(new SubmitEvent("submit", { bubbles: true, cancelable: true })));
  await page.waitForSelector("[role='status']");
  await setValue("input[aria-label='Global search']", "fastsecond");
  await page.$eval("form[role='search']", (form) => form.dispatchEvent(new SubmitEvent("submit", { bubbles: true, cancelable: true })));
  await page.waitForFunction(() => document.querySelector(".search-result")?.textContent?.includes("Fast Result"));
  await sleep(800);
  if (!(await page.$eval(".search-result", (node) => node.textContent)).includes("Fast Result")) throw new Error("Stale request replaced newer results");
  step("Stale-request race cannot replace newer results");
  await clickText("form[role='search']", "Clear");
  if (await page.$(".search-result") || !(await page.$eval(".search-initial", (node) => node.textContent)).includes("Enter a query")) throw new Error("Clear left stale results");
  await page.evaluate(() => { window.fetch = window.__searchRealFetch; delete window.__searchRealFetch; });
  step("Clear cancels work and clears stale results");

  await submitSearch("searchPwned");
  const markupSafety = await page.evaluate(() => ({
    pwned: window.__searchPwned,
    scriptCount: document.querySelectorAll(".search-results-list script").length,
    imageCount: document.querySelectorAll(".search-results-list img").length,
    text: document.querySelector(".search-results-list")?.textContent,
  }));
  if (markupSafety.pwned !== undefined || markupSafety.scriptCount || markupSafety.imageCount || !markupSafety.text.includes("<script>")) {
    throw new Error("Malicious result text did not remain inert and visible");
  }
  step("Script, handler, quote, and angle-bracket result text remains inert");

  const searchOnlyBaseline = collectFiles(join(sandbox, "Database"));
  const sandboxDb = join(sandbox, "Database/Main/family.db");
  chmodSync(sandboxDb, 0o444);
  chmodSync(journalPath, 0o444);
  try {
    await submitSearch("cobalt compass search phrase");
    if (!(await searchResults()).some((row) => row.id === `journal:${DEFAULT_PERSON_ID}`)) throw new Error("Read-only source search failed");
  } finally {
    chmodSync(sandboxDb, 0o666);
    chmodSync(journalPath, 0o666);
  }
  const searchOnlyAfter = collectFiles(join(sandbox, "Database"));
  if (!sameManifest(searchOnlyBaseline, searchOnlyAfter)) throw new Error("Search mutated sandbox DataRoot content");
  if (sha256(journalPath) !== createHash("sha256").update(searchJournal).digest("hex").toUpperCase()) throw new Error("Journal search mutated source bytes");
  if (consoleErrors.length || responseErrors.length) {
    throw new Error(`Unexpected browser errors: ${[...consoleErrors, ...responseErrors].join(" | ")}`);
  }
  step("Read-only sources search successfully; sandbox hashes stay exact; console has zero errors");

  if (passed !== 42) throw new Error(`Expected exactly 42 Search checks, recorded ${passed}`);
  console.log(`Search E2E passed: ${passed}/42`);
} finally {
  if (browser) await browser.close();
  stopProcess(vite);
  stopProcess(backend);
  try { chmodSync(join(sandbox, "Database/Main/family.db"), 0o666); } catch {}
  try { chmodSync(journalPath, 0o666); } catch {}
  verifyProduction();
  rmSync(sandbox, { recursive: true, force: true });
}
