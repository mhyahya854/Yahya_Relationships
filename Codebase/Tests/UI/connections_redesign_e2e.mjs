import puppeteer from "puppeteer-core";
import { createHash } from "node:crypto";
import { execFileSync, spawn } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { CONNECTIONS_FIXTURE_EXPECTED_PEOPLE, seedConnectionsRedesignFixture } from "./connections_redesign_fixture.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const CODEBASE = resolve(HERE, "../..");
const REPO = resolve(CODEBASE, "..");
const OUT = process.env.CONNECTIONS_REDESIGN_SCREENSHOT_DIR
  ? resolve(process.env.CONNECTIONS_REDESIGN_SCREENSHOT_DIR)
  : resolve(REPO, "Documentation/UI-Screenshots/Connections-Final-Polish");
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

async function reserveLoopbackPort() {
  return new Promise((resolvePort, rejectPort) => {
    const server = createServer();
    server.once("error", rejectPort);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (!address || typeof address === "string") {
        server.close(() => rejectPort(new Error("Could not reserve a loopback test port.")));
        return;
      }
      server.close((error) => error ? rejectPort(error) : resolvePort(address.port));
    });
  });
}

// This suite must never attach to a developer's existing localhost stack. A
// private backend/Vite pair keeps the fixture, bootstrap pointer, and browser
// traffic isolated even when the application is already running locally.
const backendPort = await reserveLoopbackPort();
const vitePort = await reserveLoopbackPort();
const apiOrigin = `http://127.0.0.1:${backendPort}`;
const webOrigin = `http://127.0.0.1:${vitePort}`;

mkdirSync(OUT, { recursive: true });
mkdirSync(dirname(bootstrap), { recursive: true });

const env = {
  ...process.env,
  PYTHONUTF8: "1",
  PYTHONPATH: [resolve(CODEBASE, "App"), resolve(CODEBASE, "Scripts"), CODEBASE, process.env.PYTHONPATH]
    .filter(Boolean).join(process.platform === "win32" ? ";" : ":"),
  PEOPLE_RELATIONSHIPS_BOOTSTRAP: bootstrap,
  PR_BACKEND_PORT: String(backendPort),
  VITE_BACKEND_URL: apiOrigin,
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
  const response = await fetch(`${apiOrigin}${path}`, init);
  const payload = await response.json();
  if (!response.ok) throw new Error(`${path}: ${JSON.stringify(payload)}`);
  return payload;
}
async function post(path, body) {
  return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}
async function shot(name, metadata) {
  const file = `${titleCaseFile(name)}.png`;
  // React Flow receives the route overlay one render after a target card
  // resolves its path request. Wait through the transition so a screenshot
  // records the composed graph rather than an intermediate frame.
  await sleep(1100);
  await page.evaluate(() => new Promise((resolveStable) => {
    const root = document.querySelector(".relationship-graph-stage");
    if (!root) { resolveStable(); return; }
    let settleTimer;
    const settle = () => {
      observer.disconnect();
      resolveStable();
    };
    const schedule = () => {
      clearTimeout(settleTimer);
      settleTimer = setTimeout(settle, 700);
    };
    const observer = new MutationObserver(schedule);
    observer.observe(root, { subtree: true, childList: true, attributes: true, characterData: true });
    schedule();
  }));
  await page.evaluate(() => new Promise((resolveFrame) => requestAnimationFrame(() => requestAnimationFrame(resolveFrame))));
  // Chromium can return from a first compositor capture immediately before
  // React Flow flushes a path-overlay paint. Prime that compositor pass, then
  // write the actual evidence image on the next frame.
  const staging = join(OUT, `.${file}.staging.png`);
  await page.screenshot({ path: staging });
  await page.evaluate(() => new Promise((resolveFrame) => requestAnimationFrame(resolveFrame)));
  await sleep(250);
  await page.screenshot({ path: join(OUT, file) });
  rmSync(staging, { force: true });
  if (process.env.CONNECTIONS_REDESIGN_DEBUG === "1") {
    const nodes = await page.$$eval(".react-flow__node", (elements) => elements.map((element) => ({
      text: element.textContent?.replace(/\s+/g, " ").trim(),
      className: element.className,
      style: (() => { const style = getComputedStyle(element); return { opacity: style.opacity, display: style.display, visibility: style.visibility, transform: style.transform }; })(),
      rect: (() => { const rect = element.getBoundingClientRect(); return { x: rect.x, y: rect.y, width: rect.width, height: rect.height }; })(),
    })));
    writeFileSync(join(OUT, `${titleCaseFile(name)}.nodes.json`), JSON.stringify(nodes, null, 2), "utf8");
  }
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
  if (!await page.$(".connections-search-dock .person-search input")) {
    await page.click("[aria-label='Open Connections search']");
  }
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
  // A TO card mounts before its canonical paths arrive. Capturing in that
  // transient state can race React Flow's path-overlay render and produce a
  // misleading half-composed canvas.
  await page.waitForFunction((expected) => {
    const card = [...document.querySelectorAll(".relationship-target-card")].find((item) => item.textContent?.includes(expected));
    return Boolean(card && (card.querySelector(".target-path-option") || card.textContent?.includes("No supported route")));
  }, { timeout: 16000 }, name);
}
async function setFromFromSearch(name) {
  await searchPick(name);
  await clickText(".connections-search-actions", "Set as FROM");
  await page.waitForFunction((expected) => document.querySelector(".builder-from-zone")?.textContent?.includes(expected), { timeout: 16000 }, name);
}
async function clearTo() {
  const clear = await page.$(".connection-builder .connection-builder-head .btn");
  if (clear && await clear.evaluate((button) => button.textContent?.includes("Clear TO"))) {
    await clear.click();
    await page.waitForFunction(() => document.querySelectorAll(".relationship-target-card").length === 0, { timeout: 12000 });
  }
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
    "# Connections Final Polish Screenshot Manifest",
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
  vite = spawn(process.execPath, [resolve(CODEBASE, "App/Frontend/node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", String(vitePort), "--strictPort"], {
    cwd: resolve(CODEBASE, "App/Frontend"), env, stdio: "pipe",
  });
  backend.stderr.on("data", (data) => { if (/Traceback|ERROR/.test(data.toString())) errors.push(data.toString()); });
  vite.stderr.on("data", (data) => { if (/error/i.test(data.toString())) errors.push(data.toString()); });
  await waitForUrl(`${apiOrigin}/api/health`);
  await waitForUrl(webOrigin);

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
  await page.goto(webOrigin, { waitUntil: "networkidle0", timeout: 40000 });
  await page.waitForSelector(".connection-builder", { visible: true, timeout: 20000 });
  await page.waitForSelector(".react-flow__node", { visible: true, timeout: 20000 });
  await sleep(1200);
  const initialNodeCount = await page.$$eval(".react-flow__node", (nodes) => nodes.length);
  assert(initialNodeCount === defaultGraph.nodes.length, `Default graph must show only immediate neighbours (${initialNodeCount} != ${defaultGraph.nodes.length}).`);
  const initialZoom = Number(await page.$eval(".graph-zoom-value", (value) => value.textContent?.replace("%", "") ?? "0"));
  assert(initialZoom >= 60, `Default Connections fit must stay readable (${initialZoom}% < 60%).`);
  await shot("connections-default-owner-immediate", { screen: "Connections", state: "default owner immediate view", theme: "light", from: "Mira Rahim", verify: "Central FROM, readable direct family/general neighbours only" });
  await shot("connections-maternal-paternal-compact-islands", { screen: "Connections", state: "compact contextual islands", theme: "light", from: "Mira Rahim", verify: "Maternal and paternal islands fit their direct members" });
  await shot("connections-compact-external-sector", { screen: "Connections", state: "lower external arc", theme: "light", from: "Mira Rahim", verify: "Direct external relationships form a deliberate lower sector" });
  await shot("connections-builder-compact", { screen: "Connections", state: "compact Relationship Builder", theme: "light", from: "Mira Rahim", verify: "FROM, TO, and immediate rows remain scannable" });
  await page.$eval(".theme-toggle", (button) => button.click());
  await page.waitForFunction(() => document.documentElement.dataset.theme === "dark");
  await shot("connections-dark-default", { screen: "Connections", state: "default owner immediate view", theme: "dark", from: "Mira Rahim", verify: "Direct context and compact islands remain readable" });
  await page.$eval(".theme-toggle", (button) => button.click());
  await page.waitForFunction(() => document.documentElement.dataset.theme === "light");

  // Adaptive packing must make a small alternate world compact and a denser
  // alternate world spacious without falling back to a family-tree layout.
  await setFromFromSearch("Mariam Rahal");
  const mariamGraph = await api(`/api/relationships/graph/neighbors/${fixture.people.mariam.id}?perspective_id=${fixture.people.mariam.id}&filters=parents,children,siblings,spouses,general`);
  await page.waitForFunction((count) => document.querySelectorAll(".react-flow__node").length === count, { timeout: 16000 }, mariamGraph.nodes.length);
  await shot("connections-alternate-from-few", { screen: "Connections", state: "alternate FROM with few direct connections", theme: "light", from: "Mariam Rahal", verify: "Small direct world remains close to FROM" });
  await clickText(".builder-from-zone", "Return to My Perspective");
  await page.waitForFunction(() => document.querySelector(".builder-from-zone")?.textContent?.includes("Mira Rahim"), { timeout: 16000 });
  await setFromFromSearch("Darya Sol");
  const daryaGraph = await api(`/api/relationships/graph/neighbors/${fixture.people.darya.id}?perspective_id=${fixture.people.darya.id}&filters=parents,children,siblings,spouses,general`);
  assert(daryaGraph.nodes.length > mariamGraph.nodes.length, "Synthetic alternate dense FROM must have more direct context than the compact fixture person.");
  await page.waitForFunction((count) => document.querySelectorAll(".react-flow__node").length === count, { timeout: 16000 }, daryaGraph.nodes.length);
  await shot("connections-alternate-from-many", { screen: "Connections", state: "alternate FROM with dense direct context", theme: "light", from: "Darya Sol", verify: "Dense direct world expands without losing central readability" });
  await clickText(".builder-from-zone", "Return to My Perspective");
  await page.waitForFunction(() => document.querySelector(".builder-from-zone")?.textContent?.includes("Mira Rahim"), { timeout: 16000 });

  // Ordinary node body selection must not open person information.
  await (await nodeCard("Darya Sol")).click();
  await sleep(350);
  assert(!await page.$(".person-info-drawer"), "Node body click opened the information drawer.");
  const daryaInfo = await (await nodeCard("Darya Sol")).$(".person-node-info");
  if (!daryaInfo) throw new Error("Darya's explicit information button was not rendered.");
  await daryaInfo.click();
  await page.waitForSelector(".person-info-drawer", { visible: true });
  await page.waitForFunction(() => document.querySelector(".person-info-drawer")?.textContent?.includes("Darya Sol"));
  const expectedTabs = ["Overview", "Relationships", "Relationship Paths", "Memories", "Events", "Photos & Videos", "Conversations", "Documents", "Places / Travel", "Groups", "Journal / Notes"];
  assert(await page.$$eval(".person-info-tabs button", (buttons, labels) => labels.every((label) => buttons.some((button) => button.textContent?.trim() === label)), expectedTabs), "The complete Connections information tab architecture was not rendered.");
  await shot("connections-info-overview", { screen: "Connections", state: "explicit info drawer overview", theme: "light", from: "Mira Rahim", verify: "ⓘ only information entry point and real Overview fields" });
  await clickText(".person-info-tabs", "Relationships");
  await shot("connections-info-relationships", { screen: "Connections", state: "explicit information drawer relationships", theme: "light", from: "Mira Rahim", verify: "Implemented relationship facts are distinct from future boundaries" });
  await clickText(".person-info-tabs", "Relationship Paths");
  await page.waitForSelector(".drawer-path-list", { visible: true, timeout: 12000 });
  await shot("connections-info-relationship-paths", { screen: "Connections", state: "canonical paths information tab", theme: "light", from: "Mira Rahim", verify: "Relationship Paths is a dedicated visible drawer tab" });
  await clickText(".person-info-tabs", "Memories");
  await page.waitForFunction(() => document.querySelector(".drawer-synthetic-boundary")?.textContent?.includes("catalogued the community orchestra archive"));
  await shot("connections-info-memories", { screen: "Connections", state: "synthetic Memories drawer boundary", theme: "light", from: "Mira Rahim", verify: "Clearly labelled synthetic future-domain preview" });
  await clickText(".person-info-tabs", "Events");
  await shot("connections-info-events", { screen: "Connections", state: "synthetic Events drawer boundary", theme: "light", from: "Mira Rahim", verify: "Clearly labelled synthetic future-domain preview" });
  await clickText(".person-info-tabs", "Photos & Videos");
  await shot("connections-info-photos-videos", { screen: "Connections", state: "synthetic Photos & Videos drawer boundary", theme: "light", from: "Mira Rahim", verify: "No production media is fabricated" });
  await clickText(".person-info-tabs", "Conversations");
  await shot("connections-info-conversations", { screen: "Connections", state: "synthetic Conversations drawer boundary", theme: "light", from: "Mira Rahim", verify: "Conversations remains an honest synthetic-only boundary" });
  await clickText(".person-info-tabs", "Documents");
  await shot("connections-info-documents", { screen: "Connections", state: "synthetic Documents drawer boundary", theme: "light", from: "Mira Rahim", verify: "Documents remains an honest synthetic-only boundary" });
  await clickText(".person-info-tabs", "Places / Travel");
  await shot("connections-info-places-travel", { screen: "Connections", state: "synthetic Places / Travel drawer boundary", theme: "light", from: "Mira Rahim", verify: "Places / Travel is a dedicated visible drawer tab" });
  await clickText(".person-info-tabs", "Groups");
  await shot("connections-info-groups", { screen: "Connections", state: "implemented Groups drawer tab", theme: "light", from: "Mira Rahim", verify: "Real supported group content stays distinct from future domains" });
  await clickText(".person-info-tabs", "Journal / Notes");
  await shot("connections-info-journal-notes", { screen: "Connections", state: "implemented Journal / Notes drawer tab", theme: "light", from: "Mira Rahim", verify: "Real synthetic journal is available through its dedicated tab" });
  await page.click("[aria-label='Close person information']");
  await page.waitForFunction(() => !document.querySelector(".person-info-drawer"));
  assert(await page.$(".connection-builder"), "Closing info did not restore the mounted builder.");

  await searchPick("Darya Sol");
  await shot("connections-search-popover", { screen: "Connections", state: "compact search result actions", theme: "light", from: "Mira Rahim", verify: "Search remains a compact popover with Set as FROM and Add to TO" });
  await clickText(".connections-search-actions", "Add to TO");
  await page.waitForSelector(".relationship-target-card", { visible: true, timeout: 16000 });
  await page.waitForFunction(() => {
    const card = document.querySelector(".relationship-target-card");
    return Boolean(card && (card.querySelector(".target-path-option") || card.textContent?.includes("No supported route")));
  }, { timeout: 16000 });
  const longNameCheck = await page.$eval(".person-node-card", (node) => {
    const match = [...document.querySelectorAll(".person-node-card")].find((card) => card.textContent?.includes("Community Orchestra Archivist"));
    if (!match) return null;
    const name = match.querySelector(".person-node-name");
    return { width: match.getBoundingClientRect().width, clamp: name ? getComputedStyle(name).webkitLineClamp : "" };
  });
  assert(Boolean(longNameCheck && longNameCheck.width <= 224.5 && longNameCheck.clamp === "2"), "Long-name node handling must stay fixed-width and two-line clamped.");
  await shot("connections-one-direct-to", { screen: "Connections", state: "one direct friend target", theme: "light", from: "Mira Rahim", to: "Darya Sol", verify: "Direct TO remains strong while context stays mounted" });
  await shot("connections-greyed-context", { screen: "Connections", state: "active direct route with context", theme: "light", from: "Mira Rahim", to: "Darya Sol", verify: "Unrelated nodes stay mounted and visibly greyed" });
  assert((await page.$$(".react-flow__node.rf-dim")).length > 0, "Unrelated graph context was not greyed while a TO route is active.");
  assert((await page.$$eval(".react-flow__node", (nodes) => nodes.length)) >= initialNodeCount, "Unrelated graph context disappeared after adding TO.");
  // Closing information must not discard the active TO route or the graph.
  const targetCardHandle = await page.evaluateHandle(() => [...document.querySelectorAll(".relationship-target-card")].find((card) => card.textContent?.includes("Darya Sol")) ?? null);
  const targetCard = targetCardHandle.asElement();
  const routeInfo = await targetCard?.$(".builder-info-button");
  if (!routeInfo) throw new Error("Darya's explicit information button was not rendered during path mode.");
  await routeInfo.click();
  await page.waitForSelector(".person-info-drawer", { visible: true });
  await page.click("[aria-label='Close person information']");
  await page.waitForFunction(() => !document.querySelector(".person-info-drawer"));
  assert(await page.$(".relationship-target-card"), "Closing info discarded the active TO state.");
  await shot("connections-builder-compact-path-state", { screen: "Connections", state: "compact TO and path rows", theme: "light", from: "Mira Rahim", to: "Darya Sol", verify: "Builder path rows remain compact and scannable" });

  await clearTo();
  await addTo("Mila Rahal-Calder");
  await shot("connections-one-distant-to", { screen: "Connections", state: "one distant mixed route", theme: "light", from: "Mira Rahim", to: "Mila Rahal-Calder", verify: "Neutral intermediates appear without removing immediate context" });

  await clearTo();
  await addTo("Maeve Rowan");
  await shot("connections-family-multipath", { screen: "Connections", state: "one family target with multiple paths", theme: "light", from: "Mira Rahim", to: "Maeve Rowan", verify: "Multiple canonical maternal and paternal routes remain independently visible" });
  const maevePathOptions = await page.$$eval(".relationship-target-card", (cards) => [...cards].find((card) => card.textContent?.includes("Maeve Rowan"))?.querySelectorAll(".target-path-option").length ?? 0);
  assert(maevePathOptions >= 2, "Expected multiple canonical paths for the synthetic multipath target.");
  await page.evaluate(() => {
    const card = [...document.querySelectorAll(".relationship-target-card")].find((item) => item.textContent?.includes("Maeve Rowan"));
    const input = card?.querySelectorAll("input[type='checkbox']")[1];
    if (!(input instanceof HTMLInputElement)) throw new Error("Second Maeve route option was unavailable.");
    input.click();
  });
  await page.waitForFunction(() => document.querySelectorAll(".relationship-target-card input[type='checkbox']:checked").length === 1, { timeout: 12000 });
  await page.waitForFunction(() => document.querySelectorAll(".rf-edge-path-active").length > 0
    && document.querySelectorAll(".target-path-option.is-selected").length === 1
    && document.querySelectorAll(".target-path-option:not(.is-selected)").length > 0, { timeout: 12000 });
  await shot("connections-one-selected-path", { screen: "Connections", state: "one selected route among valid multipath routes", theme: "light", from: "Mira Rahim", to: "Maeve Rowan", verify: "Selected route is strongest; alternate valid route remains lighter" });

  await addTo("Darya Sol");
  await addTo("Mila Rahal-Calder");
  await shot("connections-multi-target", { screen: "Connections", state: "three simultaneous targets", theme: "light", from: "Mira Rahim", to: "Maeve Rowan; Darya Sol; Mila Rahal-Calder", verify: "Per-target compact route rows and union highlighting" });
  assert((await page.$$(".relationship-target-card")).length === 3, "TO must support zero-to-many simultaneous targets.");
  const routeNodes = await page.$$eval(".react-flow__node.rf-path-intermediate", (nodes) => nodes.length);
  assert(routeNodes > 0, "Distant route did not expose neutral full-opacity intermediate nodes.");
  assert((await page.$$(".react-flow__node.rf-path-intermediate.rf-node-to")).length === 0, "An intermediate path node received TO emphasis.");

  await page.$eval(".theme-toggle", (button) => button.click());
  await page.waitForFunction(() => document.documentElement.dataset.theme === "dark");
  await shot("connections-dark-path-state", { screen: "Connections", state: "multiple targets dark mode", theme: "dark", from: "Mira Rahim", to: "Maeve Rowan; Darya Sol; Mila Rahal-Calder", verify: "Readable cards, dimming, selected routes, and compact path rows" });
  await page.click("[aria-label='Collapse sidebar']");
  await page.waitForFunction(() => document.querySelector(".shell")?.classList.contains("sidebar-collapsed"));
  await shot("connections-collapsed-navigation", { screen: "Connections", state: "collapsed navigation", theme: "dark", from: "Mira Rahim", to: "Maeve Rowan; Darya Sol; Mila Rahal-Calder", verify: "Builder and graph survive shell navigation collapse" });

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
