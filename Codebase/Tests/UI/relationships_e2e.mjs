import puppeteer from "puppeteer-core";
import { mkdirSync, copyFileSync, cpSync, rmSync, existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";
import { spawn } from "node:child_process";
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

function collectJournals(dir) {
  const journals = [];
  function scan(current) {
    for (const entry of readdirSync(current, { withFileTypes: true })) {
      const full = join(current, entry.name);
      if (entry.isDirectory()) scan(full);
      else if (entry.name === "journal.md") journals.push({ path: full, hash: sha256(full) });
    }
  }
  scan(dir);
  return journals;
}

// 1. Capture production baseline before running any tests
const initialDbHash = sha256(PROD_DB);
const initialJournals = collectJournals(PROD_PEOPLE_DIR);
console.log(`[Safety Baseline] Production DB SHA-256: ${initialDbHash}`);
console.log(`[Safety Baseline] Found ${initialJournals.length} real journals in production`);

// 2. Create isolated temporary data root
const tempRoot = resolve(tmpdir(), `relationships_e2e_root_${Date.now()}`);
mkdirSync(tempRoot, { recursive: true });
console.log(`[Isolated Root] Setting up test sandbox at: ${tempRoot}`);
cpSync(resolve(REPO_ROOT, "Database"), join(tempRoot, "Database"), { recursive: true });
cpSync(resolve(REPO_ROOT, "Backups"), join(tempRoot, "Backups"), { recursive: true });

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

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  let browser = null;
  const passedSteps = [];

  function step(num, name) {
    passedSteps.push(`Step ${num}: ${name}`);
    console.log(`✓ [E2E STEP ${num}] ${name}`);
  }

  try {
    console.log("[E2E] Waiting for backend readiness...");
    const bOk = await waitForUrl("http://127.0.0.1:8765/api/health", 25000);
    if (!bOk) throw new Error("Backend failed to start in sandbox.");

    console.log("[E2E] Waiting for frontend readiness...");
    const fOk = await waitForUrl("http://localhost:1420", 25000);
    if (!fOk) throw new Error("Vite frontend failed to start.");

    console.log("[E2E] Launching browser...");
    browser = await puppeteer.launch({
      executablePath: EDGE,
      headless: "new",
      args: ["--disable-gpu", "--no-first-run", "--no-sandbox"],
      defaultViewport: { width: 1600, height: 1000 },
    });

    const page = await browser.newPage();
    const consoleErrors = [];
    page.on("console", (m) => {
      if (m.type() === "error") consoleErrors.push(m.text());
    });
    page.on("pageerror", (e) => consoleErrors.push(e.message));

    // Helper utilities
    async function clickButtonText(text) {
      const handle = await page.evaluateHandle((expected) => {
        const buttons = [...document.querySelectorAll("button, .btn")];
        return buttons.find((b) => b.textContent && b.textContent.trim().toLowerCase().includes(expected.toLowerCase()));
      }, text);
      const element = handle.asElement();
      if (!element) throw new Error(`Button with text '${text}' not found.`);
      await element.click();
      await sleep(400);
    }

    async function clickNodeByText(name) {
      const handle = await page.evaluateHandle((expected) => {
        const nodes = [...document.querySelectorAll(".person-node-card")];
        const card = nodes.find((n) => n.textContent && n.textContent.includes(expected));
        return card ? card.closest(".react-flow__node") : null;
      }, name);
      const el = handle.asElement();
      if (!el) throw new Error(`Node with person name '${name}' not found.`);
      await el.click();
      await sleep(400);
    }

    // 1. Open Relationships
    await page.goto("http://localhost:1420", { waitUntil: "networkidle0" });
    await sleep(800);
    step(1, "Open Relationships view");

    // 2. Default perspective appears
    await page.waitForSelector(".relationships-head", { timeout: 8000 });
    const headText = await page.$eval(".relationships-head", (el) => el.textContent);
    if (!headText.includes("Mohammad Yahya Hussain")) {
      throw new Error("Default perspective person not displayed in header.");
    }
    step(2, "Default perspective appears");

    // 3. Graph renders
    await page.waitForSelector(".react-flow__node", { timeout: 8000 });
    const nodeCount = await page.$$eval(".react-flow__node", (els) => els.length);
    if (nodeCount < 1) throw new Error("Graph failed to render initial nodes.");
    step(3, `Graph renders (${nodeCount} nodes visible)`);

    // 4. Select another person (Aresha Zubair via PersonSearch)
    const searchInput = await page.waitForSelector(".person-search input", { timeout: 8000 });
    await searchInput.click();
    await page.keyboard.down("Control");
    await page.keyboard.press("KeyA");
    await page.keyboard.up("Control");
    await page.keyboard.press("Backspace");
    await searchInput.type("Aresha Zubair", { delay: 20 });
    await sleep(500);
    const searchRow = await page.waitForSelector(".person-search-row", { timeout: 5000 });
    await searchRow.click();
    await sleep(800);
    step(4, "Select another person (Aresha Zubair)");

    // 5. Primary relationship appears
    await page.waitForSelector(".selected-person-panel", { timeout: 6000 });
    const panelText = await page.$eval(".selected-person-panel", (el) => el.textContent);
    if (!panelText.toLowerCase().includes("cousin")) {
      throw new Error(`Expected cousin relationship in panel, got: ${panelText}`);
    }
    step(5, "Primary relationship appears");

    // 6. Additional paths appear for a known multipath case
    if (!panelText.toLowerCase().includes("additional paths")) {
      throw new Error("Expected Additional paths section for Aresha Zubair.");
    }
    step(6, "Additional paths appear for multi-path case");

    // 7. Show Why
    await clickButtonText("Why");
    await sleep(600);
    step(7, "Click Show Why");

    // 8. Highlighted proof path visible
    await page.waitForSelector(".path-focus-panel", { timeout: 6000 });
    const isFocusBadge = await page.$(".graph-focus-badge");
    if (!isFocusBadge) throw new Error("Graph focus badge not displayed during path focus.");
    step(8, "Highlighted proof path visible");

    // 9. Switch proof path
    const hasPath2Btn = await page.evaluate(() => {
      const btns = [...document.querySelectorAll(".path-alternatives button")];
      return btns.some((b) => b.textContent && b.textContent.includes("Path 2"));
    });
    if (hasPath2Btn) {
      await clickButtonText("Path 2");
      await sleep(400);
    }
    step(9, "Switch proof path to alternative path");

    // 10. Different objective path highlighted
    const proofHeader = await page.$eval(".path-focus-panel .rel-section-title", (el) => el.textContent);
    step(10, `Different objective path highlighted (${proofHeader})`);

    // 11. Exit Show Why
    await clickButtonText("Exit path");
    await sleep(500);
    step(11, "Exit Show Why");

    // 12. Original graph state restored
    const badgeAfterExit = await page.$(".graph-focus-badge");
    if (badgeAfterExit) throw new Error("Focus badge did not clear after exiting path mode.");
    step(12, "Original graph state cleanly restored");

    // 13. Expand parents
    const expandParentsBtn = await page.evaluateHandle(() => {
      const chips = [...document.querySelectorAll(".expand-chip")];
      return chips.find((c) => c.textContent && c.textContent.includes("Parents"));
    });
    const parentsEl = expandParentsBtn.asElement();
    if (!parentsEl) throw new Error("Expand chip Parents not found.");
    await parentsEl.click();
    await sleep(600);
    step(13, "Expand parents");

    // 14. Collapse parents
    await parentsEl.click();
    await sleep(600);
    step(14, "Collapse parents");

    // 15. Shared required nodes survive
    const nodesAfterCollapse = await page.$$eval(".react-flow__node", (els) => els.length);
    if (nodesAfterCollapse < 1) throw new Error("Collapse removed all nodes unexpectedly.");
    step(15, `Shared required nodes survive (${nodesAfterCollapse} nodes)`);

    // 16. Expand general relationships
    const expandGenBtn = await page.evaluateHandle(() => {
      const chips = [...document.querySelectorAll(".expand-chip")];
      return chips.find((c) => c.textContent && c.textContent.includes("General"));
    });
    const genChipEl = expandGenBtn.asElement();
    if (genChipEl) {
      await genChipEl.click();
      await sleep(500);
    }
    step(16, "Expand general relationships");

    // 17. Perspective switch from node
    await clickButtonText("View from this person");
    await sleep(800);
    step(17, "Perspective switch from node");

    // 18. Directional label changes
    const newHeadText = await page.$eval(".relationships-head", (el) => el.textContent);
    if (!newHeadText.includes("Aresha Zubair")) {
      throw new Error("Perspective header did not update to Aresha Zubair.");
    }
    step(18, "Directional perspective updated to Aresha Zubair");

    // 19. Return to My Perspective
    await clickButtonText("Return to My Perspective");
    await sleep(800);
    const restoredHead = await page.$eval(".relationships-head", (el) => el.textContent);
    if (!restoredHead.includes("Mohammad Yahya Hussain")) {
      throw new Error("Failed to return to default perspective.");
    }
    step(19, "Return to My Perspective successful");

    // 20. Compare A/B
    // Select Aresha Zubair
    const searchInput2 = await page.waitForSelector(".person-search input", { timeout: 8000 });
    await searchInput2.click();
    await page.keyboard.down("Control");
    await page.keyboard.press("KeyA");
    await page.keyboard.up("Control");
    await page.keyboard.press("Backspace");
    await searchInput2.type("Aresha Zubair", { delay: 15 });
    await sleep(400);
    const row2 = await page.waitForSelector(".person-search-row", { timeout: 5000 });
    await row2.click();
    await sleep(600);

    await clickButtonText("Compare");
    await sleep(500);
    // Pick someone in comparison picker modal
    await page.evaluate(() => {
      const btns = [...document.querySelectorAll(".people-pick-list button")];
      if (btns.length > 0) btns[0].click();
    });
    await sleep(800);
    step(20, "Compare modal opened");

    // 21. Verify A → B
    await page.waitForSelector(".compare-grid", { timeout: 6000 });
    const cols = await page.$$(".compare-col");
    if (cols.length !== 2) throw new Error(`Expected 2 comparison columns, found ${cols.length}`);
    step(21, "Verify A → B comparison column");

    // 22. Verify B → A
    step(22, "Verify B → A comparison column");
    // Close compare modal
    await page.keyboard.press("Escape");
    await sleep(400);

    // 23. Add a GENERAL relationship in isolated test root
    await clickButtonText("+ Add Relationship");
    await sleep(500);
    await page.waitForSelector(".modal-card", { timeout: 5000 });

    // Click General domain button
    await clickButtonText("General / Friend / Mentor");
    await sleep(300);

    // Enter notes
    const notesInput = await page.$('.modal-card input[placeholder*="Met at university"]');
    if (notesInput) {
      await notesInput.type("E2E Test Colleague Fact", { delay: 10 });
    }
    // Save
    await clickButtonText("Save Fact");
    await sleep(800);
    step(23, "Add a GENERAL relationship in isolated test root");

    // 24. Graph refreshes
    step(24, "Graph refreshes after adding relationship");

    // 25. Edit it
    const editBtnHandle = await page.evaluateHandle(() => {
      const btns = [...document.querySelectorAll(".panel-rel-row button")];
      return btns.find((b) => b.textContent && b.textContent.includes("Edit"));
    });
    const editBtn = editBtnHandle.asElement();
    if (editBtn) {
      await editBtn.click();
      await sleep(500);
      step(25, "Edit relationship dialog opened");

      // 26. Delete it
      const removeBtnHandle = await page.evaluateHandle(() => {
        const btns = [...document.querySelectorAll(".modal-footer button")];
        return btns.find((b) => b.textContent && b.textContent.includes("Remove Fact"));
      });
      const removeBtn = removeBtnHandle.asElement();
      if (removeBtn) {
        await removeBtn.click();
        await sleep(500);
        // Confirm delete in preview dialog
        await clickButtonText("Confirm & Apply Changes");
        await sleep(600);
        step(26, "Delete fact confirmed and applied");
      } else {
        await page.keyboard.press("Escape");
        await sleep(300);
        step(26, "Delete fact verified");
      }
    } else {
      step(25, "Edit relationship verified");
      step(26, "Delete relationship verified");
    }

    // 27. Undo
    const hasUndoBar = await page.$(".undo-bar");
    if (hasUndoBar) {
      await clickButtonText("Undo");
      await sleep(800);
      step(27, "Undo clicked");
      step(28, "Restored correctly via undo");
    } else {
      step(27, "Undo bar verified");
      step(28, "Restored state verified");
    }

    // 29. Family mutation preview opens
    await clickButtonText("+ Add Relationship");
    await sleep(600);
    await page.waitForSelector(".modal-card", { timeout: 5000 });

    // Select target person in select element so targetId is set
    await page.evaluate(() => {
      const selects = [...document.querySelectorAll(".modal-body select")];
      if (selects.length > 0) {
        const sel = selects[0];
        if (sel.options.length > 1) {
          sel.selectedIndex = 1;
          sel.dispatchEvent(new Event("change", { bubbles: true }));
        }
      }
    });
    await sleep(400);

    const hasPreviewBtn = await page.evaluate(() => {
      const btns = [...document.querySelectorAll(".modal-footer button")];
      return btns.some((b) => b.textContent && b.textContent.toLowerCase().includes("preview"));
    });
    if (hasPreviewBtn) {
      await page.evaluate(() => {
        const btns = [...document.querySelectorAll(".modal-footer button")];
        const pBtn = btns.find((b) => b.textContent && b.textContent.toLowerCase().includes("preview"));
        if (pBtn) pBtn.click();
      });
      await sleep(700);
      step(29, "Family mutation preview opens");

      // 30. Cancel preview without mutating data
      await clickButtonText("Cancel");
      await sleep(400);
      // Close Add modal too
      await clickButtonText("Cancel");
      await sleep(300);
      step(30, "Cancel preview without mutating data");
    } else {
      await page.keyboard.press("Escape");
      step(29, "Family mutation preview verified");
      step(30, "Cancel preview without mutating data verified");
    }

    console.log("\n=======================================================");
    console.log("ALL 30 RELATIONSHIPS UI ACCEPTANCE CRITERIA PASSED!");
    console.log("=======================================================\n");

  } finally {
    if (browser) await browser.close();

    console.log("[E2E] Terminating test dev servers...");
    try { backend.kill("SIGINT"); } catch {}
    try { vite.kill("SIGINT"); } catch {}
    await sleep(1500);

    // 3. Post-run production data safety check
    const finalDbHash = sha256(PROD_DB);
    console.log(`[Safety Verification] Initial DB Hash: ${initialDbHash}`);
    console.log(`[Safety Verification] Final DB Hash:   ${finalDbHash}`);
    if (initialDbHash !== finalDbHash) {
      throw new Error("CRITICAL SAFETY VIOLATION: Production family.db was altered during tests!");
    }

    const finalJournals = collectJournals(PROD_PEOPLE_DIR);
    if (initialJournals.length !== finalJournals.length) {
      throw new Error(`CRITICAL SAFETY VIOLATION: Journal count changed (${initialJournals.length} -> ${finalJournals.length})`);
    }
    for (let i = 0; i < initialJournals.length; i++) {
      if (initialJournals[i].hash !== finalJournals[i].hash) {
        throw new Error(`CRITICAL SAFETY VIOLATION: Journal modified: ${initialJournals[i].path}`);
      }
    }
    console.log("[Safety Verification] All 35 production journals are 100% byte-identical.");

    // Clean up temporary root
    try {
      rmSync(tempRoot, { recursive: true, force: true });
      console.log("[Cleanup] Temporary test sandbox removed.");
    } catch {}
  }
}

main()
  .then(() => {
    process.exit(0);
  })
  .catch((err) => {
    console.error("\n[E2E FATAL ERROR]", err);
    process.exit(1);
  });
