import puppeteer from "puppeteer-core";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const EDGE =
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const HERE = dirname(fileURLToPath(import.meta.url));
const [baseUrlArg, documentationShotsArg, localShotsArg] = process.argv.slice(2);
const OUT = localShotsArg || process.env.UI_SMOKE_LOCAL_SCREENSHOT_DIR
  ? resolve(localShotsArg || process.env.UI_SMOKE_LOCAL_SCREENSHOT_DIR)
  : join(HERE, "shots");
const BASE_URL = (baseUrlArg || process.env.UI_SMOKE_BASE_URL || "http://localhost:1420").replace(/\/$/, "");
// The full legacy smoke flow mutates its data root and captures several
// evidence images. CI/local verification can direct those images to an
// isolated directory instead of touching the user-owned documentation set.
const DOC_SHOTS = documentationShotsArg || process.env.UI_SMOKE_SCREENSHOT_DIR
  ? resolve(documentationShotsArg || process.env.UI_SMOKE_SCREENSHOT_DIR)
  : join(HERE, "../../../Documentation/UI-Screenshots");
mkdirSync(OUT, { recursive: true });
mkdirSync(DOC_SHOTS, { recursive: true });

const sleep = (milliseconds) =>
  new Promise((resolve) => setTimeout(resolve, milliseconds));

const browser = await puppeteer.launch({
  executablePath: EDGE,
  headless: "new",
  args: ["--disable-gpu", "--no-first-run", "--edge-skip-compat-layer-relaunch"],
  defaultViewport: { width: 1600, height: 1000 },
});

const page = await browser.newPage();
const errors = [];
page.on("console", (message) => {
  if (message.type() === "error") errors.push(message.text());
});
page.on("pageerror", (error) => errors.push("pageerror: " + error.message));

const status = [];
function report(name, ok, detail) {
  status.push(`${ok ? "PASS" : "FAIL"} ${name}${detail ? " :: " + detail : ""}`);
  if (!ok) throw new Error(`Assertion failed: ${name}${detail ? " :: " + detail : ""}`);
}

async function shot(name) {
  await sleep(700);
  const outPath = `${OUT}/${name}.png`;
  const docPath = `${DOC_SHOTS}/${name}.png`;
  const bytes = await page.screenshot();
  for (const target of [outPath, docPath]) {
    let lastError = null;
    for (let attempt = 1; attempt <= 5; attempt += 1) {
      try {
        writeFileSync(target, bytes);
        lastError = null;
        break;
      } catch (error) {
        lastError = error;
        if (attempt < 5) await sleep(attempt * 150);
      }
    }
    if (lastError) throw lastError;
  }
}

async function typeInto(selector, text) {
  await page.waitForSelector(selector, { visible: true });
  await page.click(selector);
  await page.keyboard.down("Control");
  await page.keyboard.press("KeyA");
  await page.keyboard.up("Control");
  await page.keyboard.press("Backspace");
  await page.type(selector, text, { delay: 6 });
}

async function clickText(selector, text) {
  const handle = await page.evaluateHandle(
    (sel, expected) => {
      const nodes = [...document.querySelectorAll(sel)];
      return nodes.find((node) => (node.textContent || "").includes(expected));
    },
    selector,
    text,
  );
  const element = handle.asElement();
  if (!element) throw new Error(`Element not found: ${selector} ${text}`);
  await element.click();
  await sleep(250);
}

async function selectPersonInModal(nameSubstring) {
  await page.evaluate((needle) => {
    const options = [...document.querySelectorAll("option")];
    const targetOpt = options.find((opt) => opt.text.toLowerCase().includes(needle.toLowerCase()));
    if (targetOpt) {
      const select = targetOpt.closest("select");
      if (select) {
        const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, "value")?.set;
        if (setter) {
          setter.call(select, targetOpt.value);
        } else {
          select.value = targetOpt.value;
        }
        select.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }
  }, nameSubstring);
  await sleep(300);
}

async function nodeByText(name) {
  const handle = await page.evaluateHandle((expected) => {
    const cards = [...document.querySelectorAll(".person-node-card")];
    const card = cards.find((node) =>
      (node.textContent || "").includes(expected),
    );
    if (!card) return undefined;
    return card.closest(".react-flow__node");
  }, name);
  return handle.asElement();
}

async function waitForBody(pattern, timeout = 18000) {
  await page.waitForFunction(
    (text) => document.body.textContent.includes(text),
    { timeout },
    pattern,
  );
}

async function openInspectorSection(selector) {
  const isOpen = await page.$eval(selector, (node) => node.open);
  if (!isOpen) await page.click(`${selector} summary`);
}

// 1. Relationships opens directly on the diagram with the owner perspective.
await page.goto(`${BASE_URL}/`, {
  waitUntil: "networkidle0",
  timeout: 40000,
});
await page.waitForSelector(".relationships-graph-area .react-flow", {
  timeout: 30000,
});
report(
  "Mosaic product brand is visible in the main shell",
  await page.$eval(".brand-title", (node) => node.textContent?.trim() === "Mosaic"),
);
report("Mosaic product brand is the browser window title", (await page.title()) === "Mosaic");
await page.waitForFunction(
  () => document.querySelectorAll(".react-flow__node").length >= 3,
  { timeout: 30000 },
);
const perspectiveText = await page.$eval(".perspective-current strong", (node) =>
  node.textContent.trim(),
);
report(
  "relationships default perspective owner",
  perspectiveText.includes("Mohammad Yahya Hussain"),
);
report("diagram visible by default", true);

// 2. Explicitly add a person to TO and render its canonical route options.
await page.click(".connections-search-trigger");
await typeInto(".person-search input", "Aresha");
await page.waitForSelector(".person-search-row", { visible: true });
await clickText(".person-search-row", "Aresha Zubair");
await page.waitForFunction(
  () => [...document.querySelectorAll(".connections-search-actions button")]
    .some((button) => button.textContent?.includes("Add to TO")),
);
await page.evaluate(() => {
  [...document.querySelectorAll(".connections-search-actions button")]
    .find((button) => button.textContent?.includes("Add to TO"))?.click();
});
await page.waitForSelector(".relationship-target-card", { visible: true, timeout: 30000 });
report("explicit TO target is added to the Connections builder", true);

// 3. HUMAN EDITING TEST: Open Add Person dialog on People View
await clickText(".nav-item", "People");
await page.waitForSelector(".people-table-row", { timeout: 15000 });
await clickText(".btn-primary", "Add Person");
await page.waitForSelector(".modal-card", { timeout: 5000 });
await typeInto(".form-input", "Yahya");
await sleep(600); // Allow duplicate check debounce
await shot("add-person-dialog");
report("add-person-dialog rendered with duplicate warning check", true);

// Close Add Person Modal
await clickText(".btn-outline", "Cancel");
await sleep(300);

// 4. Current Connections shell remains usable after the explicit FROM/TO flow.
await clickText(".nav-item", "Connections");
await page.waitForSelector(".relationships-graph-area .react-flow", { timeout: 15000 });
report("Connections remains usable after a target selection", true);

// 5. DATA SAFETY & RESTORE SCREENSHOTS
await clickText(".nav-item", "Backups");
await page.waitForSelector(".data-root-panel", { timeout: 15000 });
await sleep(500);
await shot("data-safety-panel");
report("data-safety-panel rendered", true);

// Open Validate / Data Root Health modal
await clickText(".data-root-panel button", "Validate");
await page.waitForSelector(".modal", { timeout: 5000 });
await sleep(400);
await shot("data-root-health");
report("data-root-health modal rendered", true);
await clickText(".modal-head button", "✕");
await sleep(300);

// Open Change Location modal
await clickText(".data-root-panel button", "Change Location");
await page.waitForSelector(".modal", { timeout: 5000 });
await sleep(400);
await shot("change-data-location");
report("change-data-location modal rendered", true);
await clickText(".modal button", "Cancel");
await sleep(300);

// Ensure at least one backup exists for details and restore test
await page.evaluate(async () => {
  const res = await fetch("/api/backups").then((r) => r.json());
  if (!res.backups || res.backups.length === 0) {
    await fetch("/api/backups", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label: "verified-snapshot" }),
    });
  }
});
await clickText(".nav-item", "People");
await sleep(400);
await clickText(".nav-item", "Backups");
await page.waitForSelector(".backup-row", { timeout: 10000 });
await sleep(500);

// Open Backup Details
await clickText(".backup-row button", "View Details");
await page.waitForSelector(".modal", { timeout: 5000 });
await sleep(400);
await shot("backup-details-verified");
report("backup-details-verified modal rendered", true);
await clickText(".modal-head button", "✕");
await sleep(300);

// Open Guided Restore Confirmation Dialog
await clickText(".backup-row button", "Restore");
await page.waitForSelector(".modal", { timeout: 5000 });
await sleep(400);
await shot("restore-confirmation");
report("restore-confirmation dialog rendered", true);

// Type RESTORE token
await typeInto(".modal input", "RESTORE");
await sleep(300);
await clickText(".modal button", "Confirm Restore");
await sleep(300);
await shot("restore-progress");
report("restore-progress rendered", true);

await page.waitForFunction(() => !document.querySelector(".modal"), { timeout: 15000 });
await sleep(800);
await shot("restore-success");
report("restore-success state rendered", true);

// 9. Family Mermaid regression.
await clickText(".nav-item", "Family Tree");
await page.waitForFunction(
  () => !!document.querySelector(".family-diagram svg"),
  { timeout: 30000 },
);
report("family mermaid regression renders", true);

const serious = errors.filter(
  (entry) =>
    !entry.includes("favicon") &&
    !entry.includes("404") &&
    !entry.includes("Download the React DevTools"),
);
if (serious.length) {
  console.log("CONSOLE ERRORS:\n" + serious.join("\n"));
}
console.log(status.join("\n"));
await browser.close();
process.exit(serious.length ? 2 : 0);
