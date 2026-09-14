import puppeteer from "puppeteer-core";
import { createHash } from "node:crypto";
import { execFileSync, spawn } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { CONNECTIONS_FIXTURE_EXPECTED_PEOPLE, seedConnectionsRedesignFixture } from "./connections_redesign_fixture.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const CODEBASE = resolve(HERE, "../..");
const REPO = resolve(CODEBASE, "..");
const OUT = process.env.CONNECTIONS_REDESIGN_SCREENSHOT_DIR
  ? resolve(process.env.CONNECTIONS_REDESIGN_SCREENSHOT_DIR)
  : resolve(REPO, "Documentation/UI-Screenshots/Connections-Redesign");
const EDGE = existsSync("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
  ? "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
  : "C:/Program Files/Microsoft/Edge/Application/msedge.exe";
const python = existsSync(resolve(CODEBASE, ".venv/Scripts/python.exe"))
  ? resolve(CODEBASE, ".venv/Scripts/python.exe")
  : process.platform === "win32" ? "python" : "python3";
const fixtureLoader = resolve(HERE, "connections_redesign_fixture.py");
const keepFixture = process.env.CONNECTIONS_REDESIGN_KEEP_FIXTURE === "1";
const requestedSyntheticRoot = process.env.CONNECTIONS_REDESIGN_SYNTHETIC_ROOT
  ? resolve(process.env.CONNECTIONS_REDESIGN_SYNTHETIC_ROOT)
  : null;
const syntheticRuntimeRoot = requestedSyntheticRoot
  ? resolve(dirname(requestedSyntheticRoot), `.connections-redesign-runtime-${process.pid}`)
  : resolve(tmpdir(), `connections-redesign-synthetic-${process.pid}`);
const syntheticRoot = requestedSyntheticRoot || join(syntheticRuntimeRoot, "Synthetic Connections Data");
const bootstrap = join(syntheticRuntimeRoot, "settings", "bootstrap.json");
const productionDb = resolve(REPO, "Database/Main/family.db");
const productionHash = createHash("sha256").update(readFileSync(productionDb)).digest("hex");
const shots = [];
const errors = [];

mkdirSync(OUT, { recursive: true });
mkdirSync(dirname(bootstrap), { recursive: true });

const env = {
  ...process.env,
  PYTHONUTF8: "1",
  PYTHONPATH: [resolve(CODEBASE, "App"), resolve(CODEBASE, "Scripts"), CODEBASE, process.env.PYTHONPATH]
    .filter(Boolean).join(process.platform === "win32" ? ";" : ":"),
  PEOPLE_RELATIONSHIPS_BOOTSTRAP: bootstrap,
};
delete env.PEOPLE_RELATIONSHIPS_ROOT;

const sleep = (ms) => new Promise((resolveSleep) => setTimeout(resolveSleep, ms));
function stop(child) {
  if (!child?.pid) return;
  if (process.platform === "win32") {
    try { execFileSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" }); } catch {}
  } else {
    try { child.kill("SIGKILL"); } catch {}
  }
}
async function waitForUrl(url, timeout = 30000) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    try { const response = await fetch(url); if (response.ok) return; } catch {}
    await sleep(250);
  }
  throw new Error(`Timed out waiting for ${url}`);
}
function assert(condition, message) {
  if (!condition) throw new Error(message);
}
function titleCaseFile(name) {
  return name.replaceAll("/", "_").replaceAll(" ", "-").toLowerCase();
}

let backend;
let vite;
let browser;
let page;

async function api(path, init) {
  const response = await fetch(`http://127.0.0.1:8765${path}`, init);
  const payload = await response.json();
  if (!response.ok) throw new Error(`${path}: ${JSON.stringify(payload)}`);
  return payload;
}
async function post(path, body) {
  return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}
async function shot(name, metadata) {
  const file = `${titleCaseFile(name)}.png`;
  await sleep(450);
  await page.screenshot({ path: join(OUT, file) });
  shots.push({ file, ...metadata });
}
async function nav(label) {
  await page.waitForFunction((expected) => [...document.querySelectorAll(".nav-item")].some((button) => button.textContent?.trim().startsWith(expected)), { timeout: 12000 }, label);
  await page.evaluate((expected) => [...document.querySelectorAll(".nav-item")].find((button) => button.textContent?.trim().startsWith(expected))?.click(), label);
  await sleep(600);
}
async function clickText(scope, text) {
  await page.waitForFunction((selector, expected) => [...document.querySelectorAll(`${selector} button`)].some((button) => button.textContent?.trim().includes(expected) && button.getClientRects().length), { timeout: 12000 }, scope, text);
  await page.evaluate((selector, expected) => [...document.querySelectorAll(`${selector} button`)].find((button) => button.textContent?.trim().includes(expected) && button.getClientRects().length)?.click(), scope, text);
  await sleep(450);
}
async function searchPick(name) {
  const input = await page.waitForSelector(".connections-search-dock .person-search input", { visible: true, timeout: 12000 });
  await input.click();
  await page.keyboard.down("Control");
  await page.keyboard.press("KeyA");
  await page.keyboard.up("Control");
  await page.keyboard.press("Backspace");
  await input.type(name, { delay: 8 });
  await page.waitForFunction((expected) => [...document.querySelectorAll(".person-search-row")].some((row) => row.textContent?.includes(expected)), { timeout: 12000 }, name);
  await page.evaluate((expected) => [...document.querySelectorAll(".person-search-row")].find((row) => row.textContent?.includes(expected))?.click(), name);
  await page.waitForSelector(".connections-search-actions", { visible: true, timeout: 12000 });
}
async function addTo(name) {
  await searchPick(name);
  await clickText(".connections-search-actions", "Add to TO");
  await page.waitForFunction((expected) => [...document.querySelectorAll(".relationship-target-card")].some((card) => card.textContent?.includes(expected)), { timeout: 16000 }, name);
}
async function nodeCard(name) {
  const handle = await page.evaluateHandle((expected) => [...document.querySelectorAll(".person-node-card")].find((card) => card.textContent?.includes(expected)) ?? null, name);
  const card = handle.asElement();
  if (!card) throw new Error(`Node ${name} was not visible.`);
  return card;
}
function manifest() {
  const rows = shots.map((shotInfo) => `| ${shotInfo.file} | ${shotInfo.screen} | ${shotInfo.state} | ${shotInfo.theme} | ${shotInfo.from} | ${shotInfo.to || "—"} | ${shotInfo.verify} |`);
  return [
    "# Connections Redesign Screenshot Manifest",
    "",
    "All captures were made with the isolated, deterministic Connections synthetic data root. The fixture contains only fictional records; it does not read or mutate the user’s production relationship data.",
    "",
    `- Rebuild command: \`npm run test:connections-redesign\` from \`Codebase\``,
    `- Synthetic people: ${CONNECTIONS_FIXTURE_EXPECTED_PEOPLE}`,
    "- Theme coverage: light and dark",
    "",
    "| File | Screen | State | Theme | FROM | TO | Verification |",
    "| --- | --- | --- | --- | --- | --- | --- |",
    ...rows,
    "",
    "The synthetic drawer previews are explicitly labelled as fixture content and exercise future-domain UI boundaries only; they are not production data.",
    "",
  ].join("\n");
}

try {
  backend = spawn(python, ["-m", "app.backend.main"], { cwd: CODEBASE, env, stdio: "pipe" });
  vite = spawn(process.execPath, [resolve(CODEBASE, "App/Frontend/node_modules/vite/bin/vite.js")], {
    cwd: resolve(CODEBASE, "App/Frontend"), env, stdio: "pipe",
  });
  backend.stderr.on("data", (data) => { if (/Traceback|ERROR/.test(data.toString())) errors.push(data.toString()); });
  vite.stderr.on("data", (data) => { if (/error/i.test(data.toString())) errors.push(data.toString()); });
  await waitForUrl("http://127.0.0.1:8765/api/health");
  await waitForUrl("http://localhost:1420");

  const fixture = await seedConnectionsRedesignFixture({ api, post, dataRoot: syntheticRoot, python, fixtureLoader });
  const health = await api("/api/health");
  assert(health.people === CONNECTIONS_FIXTURE_EXPECTED_PEOPLE, "Synthetic root has an unexpected person count.");
  const defaultGraph = await api(`/api/relationships/graph/neighbors/${fixture.people.mira.id}?perspective_id=${fixture.people.mira.id}&filters=parents,children,siblings,spouses,general`);
  assert(!defaultGraph.nodes.some((node) => node.id === fixture.people.maeve.id), "Distant family path leaked into the default immediate graph.");
  assert(defaultGraph.nodes.some((node) => node.id === fixture.people.darya.id), "Direct explicit friend missing from immediate graph.");

  browser = await puppeteer.launch({ executablePath: EDGE, headless: "new", defaultViewport: { width: 1600, height: 1000 }, args: ["--disable-gpu", "--no-first-run", "--no-sandbox", "--edge-skip-compat-layer-relaunch"] });
  page = await browser.newPage();
  page.on("console", (message) => {
    if (message.type() === "error" && !message.text().includes("Failed to load resource")) errors.push(message.text());
  });
  page.on("response", (response) => {
    if (response.status() >= 400 && !response.url().endsWith("/favicon.ico")) {
      errors.push(`${response.status()} ${response.url()}`);
    }
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.evaluateOnNewDocument((drawerDemo) => { window.__connectionsSyntheticDrawerDemo = drawerDemo; }, fixture.drawerDemo);
  await page.goto("http://localhost:1420", { waitUntil: "networkidle0", timeout: 40000 });
  await page.waitForSelector(".connection-builder", { visible: true, timeout: 20000 });
  await page.waitForSelector(".react-flow__node", { visible: true, timeout: 20000 });
  await sleep(1200);
  const initialNodeCount = await page.$$eval(".react-flow__node", (nodes) => nodes.length);
  assert(initialNodeCount === defaultGraph.nodes.length, `Default graph must show only immediate neighbours (${initialNodeCount} != ${defaultGraph.nodes.length}).`);
  await shot("connections-default-owner-immediate", { screen: "Connections", state: "default owner immediate view", theme: "light", from: "Mira Rahim", verify: "Central FROM, direct family/general neighbours only, builder visible" });
  await shot("connections-maternal-paternal-spacing", { screen: "Connections", state: "default spatial regions", theme: "light", from: "Mira Rahim", verify: "Separate pale maternal and paternal contextual regions" });

  // Ordinary node body selection must not open person information.
  await (await nodeCard("Darya Sol")).click();
  await sleep(350);
  assert(!await page.$(".person-info-drawer"), "Node body click opened the information drawer.");
  const daryaInfo = await (await nodeCard("Darya Sol")).$(".person-node-info");
  if (!daryaInfo) throw new Error("Darya's explicit information button was not rendered.");
  await daryaInfo.click();
  await page.waitForSelector(".person-info-drawer", { visible: true });
  await page.waitForFunction(() => document.querySelector(".person-info-drawer")?.textContent?.includes("Darya Sol"));
  await shot("connections-info-overview", { screen: "Connections", state: "explicit info drawer overview", theme: "light", from: "Mira Rahim", verify: "ⓘ only information entry point and real Overview fields" });
  await clickText(".person-info-tabs", "Memories");
  await page.waitForFunction(() => document.querySelector(".drawer-synthetic-boundary")?.textContent?.includes("catalogued the community orchestra archive"));
  await shot("connections-info-memories", { screen: "Connections", state: "synthetic Memories drawer boundary", theme: "light", from: "Mira Rahim", verify: "Clearly labelled synthetic future-domain preview" });
  await clickText(".person-info-tabs", "Events");
  await shot("connections-info-events", { screen: "Connections", state: "synthetic Events drawer boundary", theme: "light", from: "Mira Rahim", verify: "Clearly labelled synthetic future-domain preview" });
  await clickText(".person-info-tabs", "Photos & Videos");
  await shot("connections-info-media", { screen: "Connections", state: "synthetic media drawer boundary", theme: "light", from: "Mira Rahim", verify: "No production media is fabricated" });
  await page.click("[aria-label='Close person information']");
  await page.waitForFunction(() => !document.querySelector(".person-info-drawer"));
  assert(await page.$(".connection-builder"), "Closing info did not restore the mounted builder.");

  await searchPick("Darya Sol");
  await shot("connections-search-expanded", { screen: "Connections", state: "search result actions", theme: "light", from: "Mira Rahim", verify: "Search result supports reveal, Set as FROM, and Add to TO" });
  await clickText(".connections-search-actions", "Add to TO");
  await page.waitForSelector(".relationship-target-card", { visible: true, timeout: 16000 });
  await shot("connections-direct-friend-target", { screen: "Connections", state: "one direct friend target", theme: "light", from: "Mira Rahim", to: "Darya Sol", verify: "All canonical direct paths selected and context dimmed, not removed" });
  assert((await page.$$(".react-flow__node.rf-dim")).length > 0, "Unrelated graph context was not greyed while a TO route is active.");
  assert((await page.$$eval(".react-flow__node", (nodes) => nodes.length)) >= initialNodeCount, "Unrelated graph context disappeared after adding TO.");
  await shot("connections-greyed-context", { screen: "Connections", state: "active direct route with context", theme: "light", from: "Mira Rahim", to: "Darya Sol", verify: "Unrelated nodes stay mounted and visibly greyed" });

  await addTo("Maeve Rowan");
  await shot("connections-family-multipath", { screen: "Connections", state: "family target with multiple paths", theme: "light", from: "Mira Rahim", to: "Darya Sol; Maeve Rowan", verify: "Multiple canonical maternal/paternal routes listed independently" });
  const maevePathOptions = await page.$$eval(".relationship-target-card", (cards) => [...cards].find((card) => card.textContent?.includes("Maeve Rowan"))?.querySelectorAll(".target-path-option").length ?? 0);
  assert(maevePathOptions >= 2, "Expected multiple canonical paths for the synthetic multipath target.");

  await addTo("Mila Rahal-Calder");
  await shot("connections-distant-mixed-route", { screen: "Connections", state: "distant mixed family and external route", theme: "light", from: "Mira Rahim", to: "Darya Sol; Maeve Rowan; Mila Rahal-Calder", verify: "Missing intermediates appear without removing surrounding immediate context" });
  await shot("connections-multi-target-path-list", { screen: "Connections", state: "three simultaneous targets", theme: "light", from: "Mira Rahim", to: "Darya Sol; Maeve Rowan; Mila Rahal-Calder", verify: "Per-target all-route groups and union highlighting" });
  assert((await page.$$(".relationship-target-card")).length === 3, "TO must support zero-to-many simultaneous targets.");
  const routeNodes = await page.$$eval(".react-flow__node.rf-path-intermediate", (nodes) => nodes.length);
  assert(routeNodes > 0, "Distant route did not expose neutral full-opacity intermediate nodes.");

  // Prove FROM replacement and owner restoration are distinct, accessible actions.
  await searchPick("Mariam Rahal");
  await clickText(".connections-search-actions", "Set as FROM");
  await page.waitForFunction(() => document.querySelector(".builder-from-zone")?.textContent?.includes("Mariam Rahal"), { timeout: 16000 });
  await shot("connections-another-from", { screen: "Connections", state: "replacement FROM", theme: "light", from: "Mariam Rahal", to: "Darya Sol; Maeve Rowan; Mila Rahal-Calder", verify: "Exactly one FROM replaces the origin and re-queries route meaning" });
  await clickText(".builder-from-zone", "Return to My Perspective");
  await page.waitForFunction(() => document.querySelector(".builder-from-zone")?.textContent?.includes("Mira Rahim"), { timeout: 16000 });
  await shot("connections-return-owner", { screen: "Connections", state: "owner FROM restored", theme: "light", from: "Mira Rahim", to: "Darya Sol; Maeve Rowan; Mila Rahal-Calder", verify: "Return to My Perspective restores configured owner" });

  await page.$eval(".theme-toggle", (button) => button.click());
  await page.waitForFunction(() => document.documentElement.dataset.theme === "dark");
  await shot("connections-dark-theme", { screen: "Connections", state: "multiple targets dark mode", theme: "dark", from: "Mira Rahim", to: "Darya Sol; Maeve Rowan; Mila Rahal-Calder", verify: "Readable cards, dimming, regions, and route list in dark theme" });
  await page.click("[aria-label='Collapse sidebar']");
  await page.waitForFunction(() => document.querySelector(".shell")?.classList.contains("sidebar-collapsed"));
  await shot("connections-collapsed-navigation", { screen: "Connections", state: "collapsed navigation", theme: "dark", from: "Mira Rahim", to: "Darya Sol; Maeve Rowan; Mila Rahal-Calder", verify: "Builder and graph survive shell navigation collapse" });
  await page.click("[aria-label='Expand sidebar']");
  await page.$eval(".theme-toggle", (button) => button.click());
  await page.waitForFunction(() => document.documentElement.dataset.theme === "light");

  // Capture every current primary application area against the same synthetic root.
  await nav("People");
  await page.waitForSelector(".people-table-row", { timeout: 16000 });
  await shot("people-directory", { screen: "People", state: "synthetic directory", theme: "light", from: "Mira Rahim", verify: "82 fictional people and overlapping groups" });
  await nav("Family Tree");
  await page.waitForSelector(".family-diagram", { timeout: 16000 });
  await shot("family-tree", { screen: "Family Tree", state: "Mermaid family screen", theme: "light", from: "Mira Rahim", verify: "Family Tree remains a separate Mermaid experience" });
  await nav("Search");
  await page.waitForSelector(".search-view, .search-page", { timeout: 16000 });
  await shot("global-search", { screen: "Search", state: "synthetic root", theme: "light", from: "Mira Rahim", verify: "Primary search surface remains available" });
  await nav("Hermes");
  await sleep(700);
  await shot("hermes", { screen: "Hermes", state: "synthetic root", theme: "light", from: "Mira Rahim", verify: "Existing deferred tooling remains separate from Connections" });
  await nav("Backups");
  await sleep(700);
  await shot("backups", { screen: "Backups", state: "synthetic root", theme: "light", from: "Mira Rahim", verify: "Synthetic root backup surface remains available" });

  assert(errors.length === 0, `Browser/backend console errors: ${errors.join("\n")}`);
  const finalHash = createHash("sha256").update(readFileSync(productionDb)).digest("hex");
  assert(finalHash === productionHash, "Production relationship database changed during synthetic screenshot capture.");
  writeFileSync(join(OUT, "MANIFEST.md"), manifest(), "utf8");
  console.log(JSON.stringify({ screenshots: shots.length, output: OUT, syntheticRoot, people: CONNECTIONS_FIXTURE_EXPECTED_PEOPLE }, null, 2));
} finally {
  if (browser) await browser.close().catch(() => undefined);
  stop(vite);
  stop(backend);
  if (!keepFixture && !requestedSyntheticRoot && existsSync(syntheticRoot)) rmSync(syntheticRoot, { recursive: true, force: true });
  if (!keepFixture && existsSync(syntheticRuntimeRoot)) rmSync(syntheticRuntimeRoot, { recursive: true, force: true });
}
