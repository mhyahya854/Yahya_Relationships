// Isolated browser checks built from the shared fictional Mosaic fixture.

import puppeteer from "puppeteer-core";
import { execFileSync, spawn } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const CODEBASE = realpathSync.native(resolve(HERE, "../.."));
const PYTHON = existsSync(resolve(CODEBASE, ".venv/Scripts/python.exe"))
  ? resolve(CODEBASE, ".venv/Scripts/python.exe")
  : process.platform === "win32" ? "python" : "python3";
const EDGE = [
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
].find(existsSync);
const VITE = resolve(CODEBASE, "App/Frontend/node_modules/vite/bin/vite.js");
const OWNER_ID = "mira_rahim--MR01";
const COUSIN_ID = "aika_calder_rahim--ACR01";

function check(condition, message) {
  if (!condition) throw new Error(message);
}

function stop(child) {
  if (!child?.pid) return;
  if (process.platform === "win32") {
    try { execFileSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" }); } catch {}
  } else {
    try { child.kill("SIGKILL"); } catch {}
  }
}

async function port() {
  return new Promise((resolvePort, rejectPort) => {
    const server = createServer();
    server.once("error", rejectPort);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      server.close((error) => error ? rejectPort(error) : resolvePort(address.port));
    });
  });
}

const sleep = (ms) => new Promise((done) => setTimeout(done, ms));
async function ready(url, timeout = 30_000) {
  const began = Date.now();
  while (Date.now() - began < timeout) {
    try { if ((await fetch(url)).ok) return; } catch {}
    await sleep(250);
  }
  throw new Error(`Server did not become ready: ${url}`);
}

async function clickButton(page, text, scope = "body") {
  await page.waitForFunction((selector, label) =>
    [...document.querySelectorAll(`${selector} button`)]
      .some((button) => button.textContent?.trim().includes(label) && button.getBoundingClientRect().width > 0),
  { timeout: 20_000 }, scope, text);
  await page.evaluate((selector, label) =>
    [...document.querySelectorAll(`${selector} button`)]
      .find((button) => button.textContent?.trim().includes(label) && button.getBoundingClientRect().width > 0)
      ?.click(), scope, text);
}

async function navigate(page, label) {
  await clickButton(page, label, ".nav");
  await page.waitForFunction((expected) =>
    [...document.querySelectorAll(".nav-item.active")].some((item) => item.textContent?.includes(expected)),
  { timeout: 20_000 }, label);
}

async function openOwnerProfile(page) {
  await navigate(page, "People");
  await page.waitForFunction(() =>
    [...document.querySelectorAll(".people-table-row")].some((row) => row.textContent?.includes("Mira Rahim")),
  { timeout: 20_000 });
  await page.evaluate(() => [...document.querySelectorAll(".people-table-row")]
    .find((row) => row.textContent?.includes("Mira Rahim"))?.querySelector("button")?.click());
  await page.waitForSelector(".profile-modal", { visible: true, timeout: 20_000 });
}

async function saveShot(page, scenario) {
  const directory = process.env.MOSAIC_SYNTHETIC_UI_SHOTS;
  if (!directory) return;
  mkdirSync(directory, { recursive: true });
  await page.screenshot({ path: join(resolve(directory), `${scenario}.png`), fullPage: true });
}

export async function runScenario(scenario) {
  check(["smoke", "people", "relationships", "family", "search", "journals", "backups"].includes(scenario),
    `Unknown synthetic UI scenario: ${scenario}`);
  check(EDGE && existsSync(VITE), "Microsoft Edge and frontend dependencies are required");
  const sandbox = mkdtempSync(join(tmpdir(), `mosaic-${scenario}-ui-`));
  const root = join(sandbox, "Synthetic Data Root");
  const bootstrap = join(sandbox, "settings", "bootstrap.json");
  mkdirSync(dirname(bootstrap), { recursive: true });
  const backendPort = await port();
  const vitePort = await port();
  const apiOrigin = `http://127.0.0.1:${backendPort}`;
  const webOrigin = `http://127.0.0.1:${vitePort}`;
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
  let backend;
  let vite;
  let browser;
  try {
    execFileSync(PYTHON, ["-c",
      "from pathlib import Path; from Tests.synthetic_mosaic import build; import sys; build(Path(sys.argv[1]), include_backup=True)",
      root], { cwd: CODEBASE, env, stdio: "pipe" });
    writeFileSync(bootstrap, JSON.stringify({ active_root: root, updated_at: "synthetic-ui-test" }), "utf8");
    backend = spawn(PYTHON, ["-m", "app.backend.main"], { cwd: CODEBASE, env, stdio: "pipe" });
    vite = spawn(process.execPath, [VITE, "--host", "127.0.0.1", "--port", String(vitePort), "--strictPort"],
      { cwd: resolve(CODEBASE, "App/Frontend"), env, stdio: "pipe" });
    await ready(`${apiOrigin}/api/health`);
    await ready(webOrigin);
    const personResponse = await fetch(`${apiOrigin}/api/people`);
    const personPayload = await personResponse.json();
    check(personResponse.ok && personPayload.people?.length === 15, "Synthetic API did not load fifteen fictional people");
    browser = await puppeteer.launch({
      executablePath: EDGE,
      headless: "new",
      args: ["--disable-gpu", "--no-first-run", "--no-sandbox", "--edge-skip-compat-layer-relaunch"],
      defaultViewport: { width: 1440, height: 950 },
    });
    const page = await browser.newPage();
    const pageErrors = [];
    const debuggerSession = await page.createCDPSession();
    await debuggerSession.send("Runtime.enable");
    debuggerSession.on("Runtime.exceptionThrown", ({ exceptionDetails }) => {
      pageErrors.push(`${exceptionDetails.url}:${exceptionDetails.lineNumber + 1}:${exceptionDetails.columnNumber + 1} ${exceptionDetails.text}`);
    });
    page.on("pageerror", (error) => pageErrors.push(error.stack ?? error.message));
    await page.goto(webOrigin, { waitUntil: "networkidle2", timeout: 30_000 });
    try {
      await page.waitForSelector(".nav-item", { visible: true, timeout: 20_000 });
    } catch (error) {
      const visibleText = await page.evaluate(() => document.body?.innerText?.slice(0, 800) ?? "");
      throw new Error(`Navigation did not render: ${JSON.stringify({ visibleText, pageErrors })}`, { cause: error });
    }

    if (scenario === "people") {
      await openOwnerProfile(page);
      check((await page.$eval(".profile-modal", (node) => node.textContent)).includes("Mira Rahim"),
        "Fictional owner profile did not render");
    } else if (scenario === "journals") {
      await openOwnerProfile(page);
      await clickButton(page, "Journal", ".profile-modal");
      await page.waitForSelector(".journal-experience", { visible: true, timeout: 20_000 });
      check((await page.$eval(".journal-experience", (node) => node.textContent))
        .includes("garden concert"), "Fictional journal content did not render");
    } else if (scenario === "search") {
      await navigate(page, "Search");
      await page.waitForSelector(".search-bar input", { visible: true });
      await page.type(".search-bar input", "Dari");
      await clickButton(page, "Search", ".search-bar");
      await page.waitForFunction(() =>
        [...document.querySelectorAll(".search-result")].some((row) => row.textContent?.includes("Darya Sol")),
      { timeout: 20_000 });
    } else if (scenario === "family") {
      await navigate(page, "Family Tree");
      await page.waitForSelector(".family-diagram svg", { visible: true, timeout: 30_000 });
      check((await page.$eval(".family-view", (node) => node.textContent)).includes("Mira Rahim"),
        "Fictional family focus did not render");
      check((await page.$eval(".family-diagram", (node) => node.textContent)).includes("Aika"),
        "Fictional double-cousin node did not render");
      await saveShot(page, "family-overview");
      await page.waitForFunction(() => [...document.querySelectorAll(".family-diagram g.node.clickable-node")]
        .some((node) => node.textContent?.includes("Aika Calder-Rahim")), { timeout: 20_000 });
      const selected = await page.evaluate(() => {
        const node = [...document.querySelectorAll(".family-diagram g.node.clickable-node")]
          .find((element) => element.textContent?.includes("Aika Calder-Rahim"));
        node?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
        return Boolean(node);
      });
      check(selected, "Fictional cousin SVG node was not interactive");
      await page.waitForFunction(() => document.querySelector(".family-side")?.textContent?.includes("Aika Calder-Rahim"),
        { timeout: 20_000 });
      await page.waitForFunction(() => document.querySelector(".family-side")?.textContent?.includes("2 family paths"),
        { timeout: 20_000 });
    } else if (scenario === "relationships") {
      await navigate(page, "Connections");
      await page.waitForFunction(() => document.querySelectorAll(".relationship-graph-stage .react-flow__node").length >= 3,
        { timeout: 30_000 });
      await page.click(".connections-search-trigger");
      await page.type(".relationships-search-wrap input", "Aika");
      await page.waitForSelector(".person-search-row", { visible: true });
      await page.click(".person-search-row");
      await clickButton(page, "Add to TO", ".connections-search-actions");
      await page.waitForFunction(() =>
        document.querySelectorAll(".target-path-option").length === 2
        && document.querySelector(".target-path-summary")?.textContent?.includes("2 valid paths"),
      { timeout: 20_000 });
      const routeLabels = await page.$$eval(".target-path-option", (rows) => rows.map((row) => row.textContent?.toLowerCase()));
      check(routeLabels.some((label) => label.includes("maternal first cousin"))
        && routeLabels.some((label) => label.includes("paternal first cousin")),
      "Both fictional cousin routes did not render");
      await page.click(".target-path-option");
      await page.waitForFunction(() => document.querySelector(".graph-focus-badge")?.textContent?.includes("route"),
        { timeout: 20_000 });
      await saveShot(page, "relationships-paths");
      await page.click(".target-card-heading .builder-info-button");
      await page.waitForSelector(".person-info-drawer", { visible: true, timeout: 20_000 });
      await page.waitForFunction(() => !document.querySelector(".person-info-drawer")?.textContent
        ?.includes("Loading available person data"), { timeout: 20_000 });
    } else if (scenario === "backups") {
      await navigate(page, "Backups");
      await page.waitForSelector(".backup-row", { visible: true, timeout: 20_000 });
      check((await page.$eval(".backup-row", (node) => node.textContent)).includes("Synthetic fixture snapshot"),
        "Fictional verified backup did not render");
    } else {
      const screens = [
        ["People", ".people-view"], ["Connections", ".relationship-graph-stage"],
        ["Family Tree", ".family-view"], ["Search", ".search-view"],
        ["Raw", ".raw-view"], ["Hermes", ".hermes-layout"], ["Backups", ".backup-section"],
      ];
      for (const [label, selector] of screens) {
        await navigate(page, label);
        await page.waitForSelector(selector, { visible: true, timeout: 40_000 });
        console.log(`Smoke screen: ${label}`);
      }
    }
    check(pageErrors.length === 0, `Browser error: ${pageErrors.join("; ")}`);
    await saveShot(page, scenario);
    check(JSON.parse(readFileSync(bootstrap, "utf8")).active_root === root, "Test bootstrap pointer changed");
    console.log(`PASS synthetic ${scenario} UI scenario`);
  } finally {
    try { await browser?.close(); } catch {}
    stop(vite);
    stop(backend);
    if (process.env.MOSAIC_KEEP_SYNTHETIC_UI_ROOT !== "1") rmSync(sandbox, { recursive: true, force: true });
  }
}
