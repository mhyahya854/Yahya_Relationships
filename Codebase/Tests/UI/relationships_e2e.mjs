import puppeteer from "puppeteer-core";
import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";
import { execFileSync, spawn } from "node:child_process";
import { createHash } from "node:crypto";

const HERE = dirname(fileURLToPath(import.meta.url));
const CODEBASE = resolve(HERE, "../..");
const REPO = resolve(CODEBASE, "..");
const EDGE = existsSync("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
  ? "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
  : "C:/Program Files/Microsoft/Edge/Application/msedge.exe";
const python = existsSync(resolve(CODEBASE, ".venv/Scripts/python.exe"))
  ? resolve(CODEBASE, ".venv/Scripts/python.exe")
  : process.platform === "win32" ? "python" : "python3";
const productionDb = resolve(REPO, "Database/Main/family.db");
const productionPeople = resolve(REPO, "Database/People");
const sandbox = resolve(tmpdir(), `relationships-e2e-${process.pid}`);

function sha256(filePath) {
  return createHash("sha256").update(readFileSync(filePath)).digest("hex").toUpperCase();
}

function journalHashes(root) {
  const journals = [];
  function visit(directory) {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const full = join(directory, entry.name);
      if (entry.isDirectory()) visit(full);
      else if (entry.name === "journal.md") journals.push([full, sha256(full)]);
    }
  }
  visit(root);
  return journals;
}

function stop(child) {
  if (!child?.pid) return;
  if (process.platform === "win32") {
    try { execFileSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" }); } catch {}
  } else {
    try { child.kill("SIGKILL"); } catch {}
  }
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const initialDbHash = sha256(productionDb);
const initialJournals = journalHashes(productionPeople);
mkdirSync(sandbox, { recursive: true });
cpSync(resolve(REPO, "Database"), join(sandbox, "Database"), { recursive: true });
cpSync(resolve(REPO, "Backups"), join(sandbox, "Backups"), { recursive: true });

const environment = {
  ...process.env,
  PYTHONUTF8: "1",
  PYTHONPATH: [resolve(CODEBASE, "App"), resolve(CODEBASE, "Scripts"), CODEBASE, process.env.PYTHONPATH]
    .filter(Boolean).join(process.platform === "win32" ? ";" : ":"),
  PEOPLE_RELATIONSHIPS_ROOT: sandbox,
};

const sleep = (milliseconds) => new Promise((resolveSleep) => setTimeout(resolveSleep, milliseconds));
async function waitForUrl(url, timeout = 30000) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    try { if ((await fetch(url)).ok) return; } catch {}
    await sleep(250);
  }
  throw new Error(`Timed out waiting for ${url}`);
}

let backend;
let vite;
let browser;

async function main() {
  const errors = [];
  try {
    backend = spawn(python, ["-m", "app.backend.main"], { cwd: CODEBASE, stdio: "pipe", env: environment });
    vite = spawn(process.execPath, [resolve(CODEBASE, "App/Frontend/node_modules/vite/bin/vite.js")], {
      cwd: resolve(CODEBASE, "App/Frontend"), stdio: "pipe", env: environment,
    });
    await waitForUrl("http://127.0.0.1:8765/api/health");
    await waitForUrl("http://localhost:1420");

    const api = async (path) => {
      const response = await fetch(`http://127.0.0.1:8765${path}`);
      if (!response.ok) throw new Error(`${path} returned ${response.status}`);
      return response.json();
    };
    const owner = (await api("/api/people/mohammad_yahya_hussain")).person;
    const direct = await api(`/api/relationships/graph/neighbors/${owner.id}?perspective_id=${owner.id}&filters=parents,children,siblings,spouses,general`);
    const directPerson = direct.nodes.find((person) => person.id !== owner.id);
    assert(directPerson, "The production fixture must contain at least one direct connection.");

    browser = await puppeteer.launch({
      executablePath: EDGE,
      headless: "new",
      defaultViewport: { width: 1600, height: 1000 },
      args: ["--disable-gpu", "--no-first-run", "--no-sandbox", "--edge-skip-compat-layer-relaunch"],
    });
    const page = await browser.newPage();
    page.on("console", (message) => {
      if (message.type() === "error" && !message.text().includes("Failed to load resource")) errors.push(message.text());
    });
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("response", (response) => {
      if (response.status() >= 400 && !response.url().endsWith("/favicon.ico")) errors.push(`${response.status()} ${response.url()}`);
    });

    async function clickText(scope, text) {
      await page.waitForFunction((selector, expected) => [...document.querySelectorAll(`${selector} button`)]
        .some((button) => button.textContent?.includes(expected) && button.getClientRects().length), { timeout: 12000 }, scope, text);
      await page.evaluate((selector, expected) => [...document.querySelectorAll(`${selector} button`)]
        .find((button) => button.textContent?.includes(expected) && button.getClientRects().length)?.click(), scope, text);
      await sleep(350);
    }

    async function searchPick(name) {
      const input = await page.waitForSelector(".connections-search-dock .person-search input", { visible: true, timeout: 12000 });
      await input.click();
      await page.keyboard.down("Control");
      await page.keyboard.press("KeyA");
      await page.keyboard.up("Control");
      await page.keyboard.press("Backspace");
      await input.type(name, { delay: 8 });
      await page.waitForFunction((expected) => [...document.querySelectorAll(".person-search-row")]
        .some((row) => row.textContent?.includes(expected)), { timeout: 12000 }, name);
      await page.evaluate((expected) => [...document.querySelectorAll(".person-search-row")]
        .find((row) => row.textContent?.includes(expected))?.click(), name);
      await page.waitForSelector(".connections-search-actions", { visible: true, timeout: 12000 });
    }

    await page.goto("http://localhost:1420", { waitUntil: "networkidle0", timeout: 40000 });
    await page.waitForSelector(".connection-builder", { visible: true, timeout: 20000 });
    await page.waitForSelector(".react-flow__node", { visible: true, timeout: 20000 });
    const initialNodes = await page.$$eval(".react-flow__node", (nodes) => nodes.length);
    assert(initialNodes === direct.nodes.length, "Default Connections canvas must contain only the direct backend neighbours.");
    assert(await page.$eval(".builder-from-zone", (zone) => zone.textContent?.includes("Mohammad Yahya Hussain")), "Owner must be the initial FROM person.");

    // Search actions replace the single FROM person and the explicit return
    // action restores the configured owner.
    await searchPick("Aresha Zubair");
    await clickText(".connections-search-actions", "Set as FROM");
    await page.waitForFunction(() => document.querySelector(".builder-from-zone")?.textContent?.includes("Aresha Zubair"));
    await clickText(".builder-from-zone", "Return to My Perspective");
    await page.waitForFunction(() => document.querySelector(".builder-from-zone")?.textContent?.includes("Mohammad Yahya Hussain"));

    // A target is additive and its canonical paths remain independently visible.
    await searchPick("Aresha Zubair");
    await clickText(".connections-search-actions", "Add to TO");
    await page.waitForSelector(".relationship-target-card", { visible: true, timeout: 16000 });
    assert((await page.$$(".target-path-option")).length > 0, "A selected TO must expose canonical path options.");

    // Native drop uses the same FROM/TO contract as the visible drag handles.
    await page.evaluate((personId) => {
      const target = document.querySelector('[data-person-drop-zone="to"]');
      if (!target) throw new Error("TO drop zone is absent.");
      const transfer = new DataTransfer();
      transfer.setData("application/x-people-relationships-person", personId);
      transfer.setData("text/plain", personId);
      target.dispatchEvent(new DragEvent("dragover", { bubbles: true, cancelable: true, dataTransfer: transfer }));
      target.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: transfer }));
    }, directPerson.id);
    await page.waitForFunction(() => document.querySelectorAll(".relationship-target-card").length === 2, { timeout: 16000 });
    assert(await page.$eval(".builder-to-zone", (zone) => zone.textContent?.includes("2 targets")), "TO must support more than one selected person.");

    // Regular card selection is not an information entry point; only ⓘ opens the drawer.
    const node = await page.evaluateHandle((name) => [...document.querySelectorAll(".person-node-card")]
      .find((card) => card.textContent?.includes(name)) ?? null, directPerson.name);
    const nodeElement = node.asElement();
    assert(nodeElement, "Expected direct person node on the canvas.");
    await nodeElement.click();
    await sleep(250);
    assert(!await page.$(".person-info-drawer"), "Node body click must not open the person drawer.");
    const info = await page.$(".builder-from-zone .builder-info-button");
    assert(info, "FROM information button is absent.");
    await info.click();
    await page.waitForSelector(".person-info-drawer", { visible: true, timeout: 12000 });
    const tabs = await page.$$eval(".person-info-tabs button", (buttons) => buttons.map((button) => button.textContent?.trim()));
    for (const label of ["Overview", "Relationships", "Relationship Paths", "Memories", "Events", "Photos & Videos", "Conversations", "Documents", "Places / Travel", "Groups", "Journal / Notes"]) {
      assert(tabs.includes(label), `Person drawer tab is missing: ${label}`);
    }
    await page.click("[aria-label='Close person information']");
    await page.waitForFunction(() => !document.querySelector(".person-info-drawer"));
    assert(await page.$(".connection-builder"), "Closing information must preserve the builder.");

    assert(errors.length === 0, `Browser/API errors: ${errors.join("\n")}`);
    console.log("Connections redesign regression E2E passed.");
  } finally {
    if (browser) await browser.close().catch(() => undefined);
    stop(vite);
    stop(backend);
    const finalDbHash = sha256(productionDb);
    assert(finalDbHash === initialDbHash, "Production family.db changed during isolated E2E.");
    const finalJournals = journalHashes(productionPeople);
    assert(JSON.stringify(finalJournals) === JSON.stringify(initialJournals), "Production journals changed during isolated E2E.");
    if (existsSync(sandbox)) rmSync(sandbox, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error("Relationships E2E failed:", error);
  process.exitCode = 1;
});
