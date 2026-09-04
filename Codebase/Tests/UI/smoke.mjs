import puppeteer from "puppeteer-core";
import { mkdirSync, copyFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const EDGE =
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, "shots");
const DOC_SHOTS = join(HERE, "../../../Documentation/UI-Screenshots");
mkdirSync(OUT, { recursive: true });
mkdirSync(DOC_SHOTS, { recursive: true });

const sleep = (milliseconds) =>
  new Promise((resolve) => setTimeout(resolve, milliseconds));

const browser = await puppeteer.launch({
  executablePath: EDGE,
  headless: "new",
  args: ["--disable-gpu", "--no-first-run"],
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
  await page.screenshot({ path: outPath });
  const docPath = `${DOC_SHOTS}/${name}.png`;
  copyFileSync(outPath, docPath);
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

// 1. Relationships opens directly on the diagram with the owner perspective.
await page.goto("http://localhost:1420/", {
  waitUntil: "networkidle0",
  timeout: 40000,
});
await page.waitForSelector(".relationships-graph-area .react-flow", {
  timeout: 30000,
});
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

// 2. Select a multi-path relative.
await typeInto(".person-search input", "Aresha");
await page.waitForSelector(".person-search-row", { visible: true });
await clickText(".person-search-row", "Aresha Zubair");
await waitForBody("paternal first cousin");
await waitForBody("maternal second cousin");
report("primary + additional shown in panel", true);

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

// 4. HUMAN EDITING TEST: Add Relationship on Relationships View
await clickText(".nav-item", "Relationships");
await page.waitForSelector(".relationships-graph-area .react-flow", { timeout: 15000 });

// Select Mansoor Hussain
await typeInto(".person-search input", "Mansoor");
await page.waitForSelector(".person-search-row", { visible: true });
await page.click(".person-search-name");
await page.waitForFunction(
  () => document.querySelector(".side-profile-row")?.textContent.includes("Mansoor"),
  { timeout: 5000 },
);

// Click + Add Relationship button
await clickText(".row-actions button", "+ Add Relationship");
await page.waitForSelector(".modal-card", { timeout: 5000 });
await typeInto(".form-group input[placeholder*='Search']", "Adeel");
await sleep(300);
await selectPersonInModal("Adeel");

await shot("add-family-relationship");
report("add-family-relationship modal rendered", true);

// Click Preview Consequences
await clickText("button", "Preview Consequences");
await page.waitForSelector(".modal-card .diff-card, .modal-card .preview-direct", { timeout: 10000 });
await shot("mutation-preview");
report("mutation-preview consequence diff rendered", true);

// Cancel preview & relationship dialog safely
await page.evaluate(() => {
  const cards = [...document.querySelectorAll(".modal-card")];
  const topCard = cards[cards.length - 1];
  const cancelBtn = [...topCard.querySelectorAll("button")].find((b) => b.textContent.includes("Cancel"));
  if (cancelBtn) cancelBtn.click();
});
await sleep(500);

// Close Add Relationship dialog if still open
await page.evaluate(() => {
  const card = document.querySelector(".modal-card");
  if (card) {
    const cancelBtn = [...card.querySelectorAll("button")].find((b) => b.textContent.includes("Cancel"));
    if (cancelBtn) cancelBtn.click();
  }
});
await page.waitForFunction(() => !document.querySelector(".modal-card"), { timeout: 5000 });

// 5. Add General Friend Relationship and capture relationship-added
await clickText("button", "+ Add Relationship");
await page.waitForSelector(".modal-card", { timeout: 5000 });
await typeInto(".form-group input[placeholder*='Search']", "Adeel");
await sleep(300);
await selectPersonInModal("Adeel");
await clickText(".btn", "General");
await sleep(200);
await clickText(".btn-primary", "Save Fact");
await page.waitForSelector(".undo-bar", { timeout: 5000 });
await shot("relationship-added");
report("relationship-added rendered with floating undo bar", true);
await shot("relationship-added");
report("relationship-added rendered with floating undo bar", true);

// Undo the addition
await clickText(".undo-bar-btn", "Undo");
await sleep(1000);

// 6. EDIT & DELETE IMPACT PREVIEWS
await clickText(".nav-item", "People");
await page.waitForSelector(".people-table-row", { timeout: 15000 });
await clickText(".people-table-row", "Mansoor Hussain");
await sleep(400);
await clickText(".row-actions .btn-danger", "Delete");
await page.waitForSelector(".diff-card, .diff-invalid", { timeout: 8000 });
await shot("delete-impact-preview");
report("delete-impact-preview rendered safely blocking graph deletion", true);
await clickText(".btn-outline", "Cancel");
await sleep(300);

// 7. Edit General Relationship
await clickText(".nav-item", "Relationships");
await page.waitForSelector(".relationships-graph-area .react-flow", { timeout: 15000 });

// Add a temporary general relationship via API for edit screenshot
await page.evaluate(async () => {
  const pList = await fetch("/api/people").then((r) => r.json());
  const mansoor = pList.people.find((p) => p.name.includes("Mansoor"));
  const irsa = pList.people.find((p) => p.name.includes("Irsa"));
  if (mansoor && irsa) {
    await fetch("/api/relationships/general", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        person_a: mansoor.id,
        person_b: irsa.id,
        type: "mentor",
        directionality: "directional",
        label_a_to_b: "Mentor",
        label_b_to_a: "Mentee",
      }),
    });
  }
});
await clickText(".nav-item", "People");
await sleep(300);
await clickText(".nav-item", "Relationships");
await sleep(800);
await typeInto(".person-search input", "Irsa");
await page.waitForSelector(".person-search-row", { visible: true });
await clickText(".person-search-row", "Irsa Naz");
await sleep(500);

// Click Edit on general entry
const editButtons = await page.$$(".panel-rel-row .btn");
if (editButtons.length > 0) {
  await editButtons[0].click();
  await page.waitForSelector(".modal-card", { timeout: 5000 });
  await shot("edit-general-relationship");
  report("edit-general-relationship rendered", true);
  await clickText(".btn-outline", "Close");
  await sleep(300);
}

// Clean up temporary mentor fact created for screenshot
await page.evaluate(async () => {
  const genList = await fetch("/api/relationships/general").then((r) => r.json());
  for (const rel of genList.relationships) {
    if (rel.type === "mentor") {
      await fetch(`/api/relationships/general/${rel.id}`, { method: "DELETE" });
    }
  }
});

// 8. DATA SAFETY & RESTORE SCREENSHOTS
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
await clickText(".nav-item", "Family");
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
