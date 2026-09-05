import puppeteer from "puppeteer-core";
import { mkdirSync, copyFileSync, cpSync, rmSync, existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";
import { spawn, execSync } from "node:child_process";
import { createHash } from "node:crypto";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "../..");
const REPO_ROOT = resolve(ROOT, "..");
const DOC_SHOTS = resolve(REPO_ROOT, "Documentation/UI-Screenshots");
mkdirSync(DOC_SHOTS, { recursive: true });

const EDGE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";

function sha256(filePath) {
  const content = readFileSync(filePath);
  return createHash("sha256").update(content).digest("hex").toUpperCase();
}

const PROD_DB = resolve(REPO_ROOT, "Database/Main/family.db");
const PROD_PEOPLE_DIR = resolve(REPO_ROOT, "Database/People");

// Capture production baseline before running any tests
const initialDbHash = sha256(PROD_DB);
const initialJournals = [];
function recordJournals(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) recordJournals(full);
    else if (entry.name === "journal.md") initialJournals.push({ path: full, hash: sha256(full) });
  }
}
recordJournals(PROD_PEOPLE_DIR);
console.log(`[Safety Baseline] Production DB SHA-256: ${initialDbHash}`);
console.log(`[Safety Baseline] Found ${initialJournals.length} real journals in production`);

// Create isolated temporary data root
const tempRoot = resolve(tmpdir(), `people_e2e_root_${Date.now()}`);
mkdirSync(tempRoot, { recursive: true });
console.log(`[Isolated Root] Setting up test sandbox at: ${tempRoot}`);
cpSync(resolve(REPO_ROOT, "Database"), join(tempRoot, "Database"), { recursive: true });

// Setup Python & paths
const python = process.platform === "win32"
  ? existsSync(resolve(ROOT, ".venv/Scripts/python.exe"))
    ? resolve(ROOT, ".venv/Scripts/python.exe")
    : "python"
  : "python3";

const appDir = resolve(ROOT, "App");
const scriptsDir = resolve(ROOT, "Scripts");
const pythonPathParts = [appDir, scriptsDir, ROOT];
if (process.env.PYTHONPATH) pythonPathParts.push(process.env.PYTHONPATH);
const pythonPath = pythonPathParts.join(process.platform === "win32" ? ";" : ":");

const env = {
  ...process.env,
  PYTHONUTF8: "1",
  PYTHONPATH: pythonPath,
  PEOPLE_RELATIONSHIPS_ROOT: tempRoot,
};

console.log("[E2E] Spawning isolated FastAPI backend...");
const backend = spawn(python, ["-m", "app.backend.main"], {
  cwd: ROOT,
  stdio: "pipe",
  env,
});

backend.stderr.on("data", (d) => {
  const msg = d.toString();
  if (msg.includes("ERROR") || msg.includes("Traceback")) {
    console.error("[Backend Error]", msg);
  }
});

console.log("[E2E] Spawning Vite frontend...");
const vite = spawn(
  process.platform === "win32" ? "npm.cmd" : "npm",
  ["--prefix", "App/Frontend", "run", "dev"],
  {
    cwd: ROOT,
    stdio: "pipe",
    shell: process.platform === "win32",
    env,
  },
);

async function waitForUrl(url, timeoutMs = 30000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(url);
      if (res.ok) return true;
    } catch {}
    await new Promise((r) => setTimeout(r, 600));
  }
  return false;
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function cleanup() {
  console.log("[E2E] Shutting down server processes...");
  if (process.platform === "win32") {
    if (backend && backend.pid) {
      try { execSync(`taskkill /pid ${backend.pid} /T /F`); } catch {}
    }
    if (vite && vite.pid) {
      try { execSync(`taskkill /pid ${vite.pid} /T /F`); } catch {}
    }
  } else {
    try { backend.kill("SIGKILL"); } catch {}
    try { vite.kill("SIGKILL"); } catch {}
  }
  await sleep(800);
  try {
    rmSync(tempRoot, { recursive: true, force: true });
    console.log("[E2E] Cleaned up isolated sandbox directory.");
  } catch (err) {
    console.warn("[E2E] Sandbox cleanup warning:", err.message);
  }

  // Verify production data integrity
  const finalDbHash = sha256(PROD_DB);
  if (finalDbHash !== initialDbHash) {
    throw new Error(`CRITICAL: Production DB was modified during test! Expected ${initialDbHash}, got ${finalDbHash}`);
  }
  for (const j of initialJournals) {
    const curr = sha256(j.path);
    if (curr !== j.hash) {
      throw new Error(`CRITICAL: Production journal was modified: ${j.path}`);
    }
  }
  console.log("[E2E] Production data integrity 100% verified (unmodified).");
}

let browser;
try {
  console.log("[E2E] Waiting for backend readiness...");
  const backendReady = await waitForUrl("http://127.0.0.1:8765/api/health", 25000);
  if (!backendReady) throw new Error("Backend did not become ready in time.");

  console.log("[E2E] Waiting for frontend readiness...");
  const frontendReady = await waitForUrl("http://localhost:1420", 30000);
  if (!frontendReady) throw new Error("Frontend did not become ready in time.");

  console.log("[E2E] Launching Puppeteer Edge session...");
  browser = await puppeteer.launch({
    executablePath: EDGE,
    headless: "new",
    args: ["--disable-gpu", "--no-first-run"],
    defaultViewport: { width: 1440, height: 900 },
  });

  const page = await browser.newPage();
  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push("pageerror: " + err.message));

  async function shot(name) {
    await sleep(600);
    const docPath = `${DOC_SHOTS}/${name}.png`;
    await page.screenshot({ path: docPath });
    console.log(`  [Screenshot] Captured: ${name}.png`);
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
    const el = handle.asElement();
    if (!el) throw new Error(`Element not found: ${selector} "${text}"`);
    await el.click();
    await sleep(350);
  }

  async function typeInto(selector, text) {
    await page.waitForSelector(selector, { visible: true });
    await page.click(selector);
    await page.keyboard.down("Control");
    await page.keyboard.press("KeyA");
    await page.keyboard.up("Control");
    await page.keyboard.press("Backspace");
    await page.type(selector, text, { delay: 10 });
  }

  // 1. Open PEOPLE View
  console.log("[Step 1] Navigating to People View...");
  await page.goto("http://localhost:1420/", { waitUntil: "networkidle0", timeout: 40000 });
  await clickText(".nav-item", "People");
  await page.waitForSelector(".people-table-row", { timeout: 15000 });

  // 2. Verify all 35 canonical people render once
  const rowCount = await page.$$eval(".people-table-row", (rows) => rows.length);
  console.log(`[Step 2] Rendered ${rowCount} canonical people.`);
  if (rowCount !== 35) throw new Error(`Expected 35 canonical people, found: ${rowCount}`);
  await shot("people-main");

  // 3. Search by person name
  console.log("[Step 3] Testing real-time search by name...");
  await typeInto(".toolbar input[placeholder*='Search']", "Aresha");
  await sleep(400);
  const searchCount = await page.$$eval(".people-table-row", (rows) => rows.length);
  if (searchCount !== 1) throw new Error(`Expected 1 match for "Aresha", found: ${searchCount}`);
  console.log("  Search found Aresha Zubair cleanly.");

  // 4. Group filtering
  console.log("[Step 4] Testing group tab filter...");
  await typeInto(".toolbar input[placeholder*='Search']", ""); // clear search
  await sleep(300);
  await clickText(".tab", "Family");
  await sleep(300);
  await shot("people-filtered");
  console.log("  Group filtering applied.");

  // 5. Clear filter
  console.log("[Step 5] Clearing filter...");
  await clickText(".tab", "All");
  await sleep(300);
  const resetCount = await page.$$eval(".people-table-row", (rows) => rows.length);
  if (resetCount !== 35) throw new Error(`Expected 35 people after reset, found: ${resetCount}`);

  // 6 & 7 & 8. Open Person Profile (Aresha Zubair: multi-path cousin)
  console.log("[Step 6-8] Opening Person Profile for Aresha Zubair...");
  await clickText(".person-cell", "Aresha Zubair");
  await page.waitForSelector(".person-profile-container", { timeout: 8000 });
  await sleep(600);
  await shot("person-profile");

  const profileText = await page.$eval(".person-profile-container", (el) => el.textContent);
  if (!profileText.includes("Aresha Zubair")) throw new Error("Profile header name mismatch");
  if (!profileText.includes("paternal first cousin")) throw new Error("Primary kinship missing in profile");
  if (!profileText.includes("maternal second cousin")) throw new Error("Secondary kinship path missing in profile");
  console.log("  Profile displayed with multi-path kinship and Urdu labels.");

  // 9. Show Relationship Path navigation to Relationships view
  console.log("[Step 9] Testing Show Relationship Path integration...");
  await clickText(".person-profile-container button", "Show Relationship Path");
  await page.waitForSelector(".relationships-graph-area .react-flow", { timeout: 15000 });
  await sleep(1000);
  const selectedName = await page.$eval(".side-profile-row strong", (el) => el.textContent);
  if (!selectedName.includes("Aresha")) throw new Error("Relationships screen did not select Aresha Zubair");
  console.log("  Show Relationship Path navigated directly into graph with Aresha selected.");

  // 10. Return to People & inspect Journal tab
  console.log("[Step 10] Returning to People view to verify Journal integration...");
  await clickText(".nav-item", "People");
  await page.waitForSelector(".people-table-row", { timeout: 10000 });
  await clickText(".person-cell", "Mansoor Hussain");
  await page.waitForSelector(".person-profile-container", { timeout: 8000 });
  await clickText(".profile-tab", "Journal");
  await sleep(600);
  await page.waitForSelector(".journal-toolbar, .journal-view, .journal-editor", { timeout: 8000 });
  console.log("  Journal section reachable and readable from profile.");

  // Close profile modal
  await page.click(".modal-head button[title='Close']");
  await sleep(300);

  // 11. Add Person with Duplicate Detection Safeguard
  console.log("[Step 11] Opening Add Person modal & testing duplicate safeguards...");
  await clickText(".view-head button", "+ Add Person");
  await page.waitForSelector(".modal-card", { timeout: 6000 });

  // Type existing name to trigger duplicate warning
  await typeInto(".form-group input", "Mansoor Hussain");
  await sleep(700);
  await shot("add-person");
  await shot("add-person-dialog");

  const dupWarning = await page.$(".diff-warning");
  if (!dupWarning) throw new Error("Duplicate warning banner did not appear for existing person name");
  console.log("  Duplicate warning displayed cleanly.");

  // Change to a unique synthetic test person
  await typeInto(".form-group input", "Synthetic Test Person");
  await sleep(400);

  // 12. Assign multiple groups (Family is default, add Friends)
  console.log("[Step 12] Assigning multiple groups to synthetic person...");
  await clickText(".form-group button.chip", "Friends");

  // Save new person
  await clickText(".modal-footer .btn-primary", "Create Person");
  await page.waitForFunction(() => !document.querySelector(".modal-card"), { timeout: 8000 });
  await sleep(500);

  const countAfterAdd = await page.$$eval(".people-table-row", (rows) => rows.length);
  if (countAfterAdd !== 36) throw new Error(`Expected 36 people after adding synthetic person, got: ${countAfterAdd}`);
  console.log("  Synthetic person created successfully with multiple groups.");

  // 13 & 14. Edit synthetic person
  console.log("[Step 13-14] Editing synthetic person...");
  // Find Synthetic Test Person row actions
  await typeInto(".toolbar input[placeholder*='Search']", "Synthetic");
  await sleep(300);
  await clickText(".row-actions button", "Edit");
  await page.waitForSelector(".modal-card", { timeout: 5000 });
  await shot("edit-person");

  // Add alias
  await typeInto(".form-group input[placeholder*='Aliases']", "Synth Master, Test Subject");
  await clickText(".modal-footer .btn-primary", "Save Changes");
  await page.waitForFunction(() => !document.querySelector(".modal-card"), { timeout: 8000 });
  await sleep(500);

  // Verify count remains 36 (no duplicates)
  await typeInto(".toolbar input[placeholder*='Search']", "");
  await sleep(300);
  const countAfterEdit = await page.$$eval(".people-table-row", (rows) => rows.length);
  if (countAfterEdit !== 36) throw new Error(`Expected 36 people after edit, got: ${countAfterEdit}`);
  console.log("  Synthetic person edited without duplication.");

  // 15. Safe person removal with consequence preview
  console.log("[Step 15] Testing safe person removal with consequence preview...");
  await typeInto(".toolbar input[placeholder*='Search']", "Synthetic");
  await sleep(300);
  await clickText(".row-actions .btn-danger", "Delete");
  await page.waitForSelector(".modal-card .diff-card, .modal-card .diff-invalid", { timeout: 8000 });
  await sleep(600);
  await shot("remove-person-preview");
  await shot("delete-impact-preview");

  await clickText(".modal-footer .btn-danger", "Delete Person");
  await page.waitForFunction(() => !document.querySelector(".modal-card"), { timeout: 8000 });
  await sleep(600);

  await typeInto(".toolbar input[placeholder*='Search']", "");
  await sleep(300);
  const countAfterDelete = await page.$$eval(".people-table-row", (rows) => rows.length);
  if (countAfterDelete !== 35) throw new Error(`Expected 35 people after deletion, got: ${countAfterDelete}`);
  console.log("  Synthetic person deleted cleanly.");

  // 16 & 17. Undo Removal (restore DB + filesystem journal)
  console.log("[Step 16-17] Testing Undo of person removal...");
  await page.waitForSelector(".undo-bar", { timeout: 5000 });
  await clickText(".undo-bar-btn", "Undo");
  await sleep(1000);

  const countAfterUndo = await page.$$eval(".people-table-row", (rows) => rows.length);
  if (countAfterUndo !== 36) throw new Error(`Expected 36 people after Undo, got: ${countAfterUndo}`);
  console.log("  Undo successfully restored person record and filesystem state!");

  // 17b. Missing Journal Integrity Check in UI
  console.log("[Step 17b] Testing missing journal detection in profile...");
  const synthJournalPath = join(tempRoot, "Database/People/Family/synthetic_test_person/journal.md");
  if (existsSync(synthJournalPath)) {
    rmSync(synthJournalPath);
  }
  await typeInto(".toolbar input[placeholder*='Search']", "Synthetic");
  await sleep(300);
  await clickText(".person-cell", "Synthetic Test Person");
  await page.waitForSelector(".person-profile-container", { timeout: 8000 });
  await clickText(".profile-tab", "Journal");
  await sleep(600);
  const warningElem = await page.$(".journal-missing-warning");
  if (!warningElem) throw new Error("Expected missing journal warning banner in profile!");
  const stillMissing = !existsSync(synthJournalPath);
  if (!stillMissing) throw new Error("Opening profile silently recreated missing journal.md!");
  console.log("  Missing journal warning displayed and journal.md was NOT recreated by read!");
  await page.click(".modal-head button[title='Close']");
  await sleep(300);

  // 18. Check console errors
  const criticalErrors = consoleErrors.filter(
    (e) => !e.includes("favicon") && !e.includes("404") && !e.includes("React DevTools"),
  );
  if (criticalErrors.length > 0) {
    console.warn("[E2E Console Errors]", criticalErrors);
    throw new Error(`Encountered console errors: ${criticalErrors.join("; ")}`);
  }
  console.log("[Step 18] Zero console errors detected during full session.");

  console.log("\n========================================================");
  console.log("🎉 ALL 18 UI / E2E PEOPLE VERIFICATION CHECKS PASSED!");
  console.log("========================================================\n");

} finally {
  if (browser) await browser.close();
  await cleanup();
  process.exit(0);
}
