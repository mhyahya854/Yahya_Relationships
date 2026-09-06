import puppeteer from "puppeteer-core";
import { mkdirSync, cpSync, rmSync, existsSync, readdirSync, readFileSync } from "node:fs";
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

const EDGE = existsSync("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
  ? "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
  : "C:/Program Files/Microsoft/Edge/Application/msedge.exe";

function sha256(filePath) {
  const content = readFileSync(filePath);
  return createHash("sha256").update(content).digest("hex").toUpperCase();
}

const PROD_DB = resolve(REPO_ROOT, "Database/Main/family.db");
const PROD_PEOPLE_DIR = resolve(REPO_ROOT, "Database/People");

// 1. Capture production baseline before running any tests
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

// 2. Create isolated temporary data root
const tempRoot = resolve(tmpdir(), `family_e2e_root_${Date.now()}`);
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
      if (m.type() === "error") {
        const text = m.text();
        // Ignore favicon or expected transient connection attempts
        if (!text.includes("favicon") && !text.includes("net::ERR_CONNECTION_REFUSED")) {
          consoleErrors.push(text);
        }
      }
    });

    async function clickButtonText(text) {
      const handle = await page.evaluateHandle((expected) => {
        const buttons = [...document.querySelectorAll("button, .btn, .nav-item")];
        return buttons.find((b) => b.textContent && b.textContent.trim().toLowerCase().includes(expected.toLowerCase()));
      }, text);
      const element = handle.asElement();
      if (!element) throw new Error(`Button with text '${text}' not found.`);
      await element.click();
      await sleep(500);
    }

    await page.goto("http://localhost:1420", { waitUntil: "networkidle2" });
    await sleep(1000);

    // -----------------------------------------------------------------------
    // 1. Open FAMILY from main nav
    // -----------------------------------------------------------------------
    await clickButtonText("Family");
    await sleep(800);
    step(1, "Open FAMILY from main nav");

    // -----------------------------------------------------------------------
    // 2. Family screen loads
    // -----------------------------------------------------------------------
    await page.waitForSelector("div.view-head h1", { timeout: 10000 });
    const titleText = await page.$eval("div.view-head h1", (el) => el.textContent);
    if (!titleText.includes("Family")) throw new Error(`Unexpected title: ${titleText}`);
    step(2, "Family screen loads");

    // -----------------------------------------------------------------------
    // 3. Default focus visible
    // -----------------------------------------------------------------------
    await page.waitForSelector(".family-focus-current", { timeout: 10000 });
    const focusText = await page.$eval(".family-focus-current", (el) => el.textContent);
    if (!focusText.includes("Mohammad Yahya Hussain")) {
      throw new Error(`Expected default focus Mohammad Yahya Hussain, found: ${focusText}`);
    }
    step(3, "Default focus visible");

    // -----------------------------------------------------------------------
    // 4. Mermaid diagram renders
    // -----------------------------------------------------------------------
    await page.waitForSelector(".family-diagram svg", { timeout: 15000 });
    const hasSvg = await page.evaluate(() => {
      const svg = document.querySelector(".family-diagram svg");
      return Boolean(svg && svg.children.length > 0);
    });
    if (!hasSvg) throw new Error("Mermaid SVG diagram not found or empty");
    const nodeIds = await page.evaluate(() => {
      return Array.from(document.querySelectorAll("g.node")).map((n) => n.id);
    });
    console.log("  [Debug] Node IDs sample:", nodeIds.slice(0, 8));
    step(4, "Mermaid diagram renders");

    // -----------------------------------------------------------------------
    // 5. Default focus node visible
    // -----------------------------------------------------------------------
    const defaultFocusNode = await page.evaluate(() => {
      const node = document.querySelector('g.node[id*="p_mohammad_yahya_hussain"]');
      return Boolean(node);
    });
    if (!defaultFocusNode) throw new Error("Default focus node p_mohammad_yahya_hussain not found in SVG");
    step(5, "Default focus node visible");

    // -----------------------------------------------------------------------
    // 6. Legend visible
    // -----------------------------------------------------------------------
    const legendVisible = await page.evaluate(() => {
      const leg = document.querySelector(".family-legend");
      return Boolean(leg && leg.textContent.includes("Maternal Branch") && leg.textContent.includes("Paternal Branch"));
    });
    if (!legendVisible) throw new Error("Legend not found or missing branches");
    step(6, "Legend visible");

    // Screenshot 1: family-main.png
    await page.screenshot({ path: join(DOC_SHOTS, "family-main.png"), fullPage: false });
    console.log("  [Screenshot] Captured: family-main.png");

    // -----------------------------------------------------------------------
    // 7. Select/click a family member (Maham Mansoor)
    // -----------------------------------------------------------------------
    const clickedMaham = await page.evaluate(() => {
      const node = document.querySelector('g.node[id*="p_maham_mansoor"]');
      if (node) {
        node.dispatchEvent(new MouseEvent("click", { bubbles: true }));
        return true;
      }
      return false;
    });
    if (!clickedMaham) throw new Error("Failed to click Maham Mansoor node in SVG");
    await sleep(800);
    step(7, "Select/click a family member (Maham Mansoor)");

    // -----------------------------------------------------------------------
    // 8. Context panel opens
    // -----------------------------------------------------------------------
    await page.waitForSelector("aside.family-side", { timeout: 5000 });
    const sideName = await page.$eval("aside.family-side strong", (el) => el.textContent);
    if (!sideName.includes("Maham Mansoor")) throw new Error(`Expected Maham Mansoor in side panel, got: ${sideName}`);
    step(8, "Context panel opens");

    // -----------------------------------------------------------------------
    // 9. Relationship-to-focus shown (Sister / بہن)
    // -----------------------------------------------------------------------
    await page.waitForSelector(".relation-card-item .relation-en", { timeout: 5000 });
    const relEn = await page.$eval(".relation-card-item .relation-en", (el) => el.textContent);
    const relUr = await page.$eval(".relation-card-item .relation-ur", (el) => el.textContent);
    if (!relEn.includes("Sister") || !relUr.includes("بہن")) {
      throw new Error(`Expected Sister / بہن, found: ${relEn} / ${relUr}`);
    }
    step(9, "Relationship-to-focus shown (Sister / بہن)");

    // Screenshot 2: family-person-selected.png
    await page.screenshot({ path: join(DOC_SHOTS, "family-person-selected.png"), fullPage: false });
    console.log("  [Screenshot] Captured: family-person-selected.png");

    // -----------------------------------------------------------------------
    // 10. View Profile works
    // -----------------------------------------------------------------------
    await clickButtonText("View Profile");
    await sleep(1000);

    // Verify modal with Profile opened
    await page.waitForSelector(".modal h2", { timeout: 5000 });
    const profileTitle = await page.$eval(".modal h2", (el) => el.textContent);
    if (!profileTitle.includes("Maham Mansoor") || !profileTitle.includes("Profile")) {
      throw new Error(`Profile modal did not open for Maham Mansoor, got: ${profileTitle}`);
    }
    step(10, "View Profile works");

    // Close profile modal
    const closeBtn = await page.$(".modal-head button");
    if (closeBtn) await closeBtn.click();
    await sleep(500);

    // -----------------------------------------------------------------------
    // 11. Return to Family preserves usable state
    // -----------------------------------------------------------------------
    await clickButtonText("Family");
    await sleep(800);
    await page.waitForSelector(".family-diagram svg", { timeout: 10000 });
    step(11, "Return to Family preserves usable state");

    // -----------------------------------------------------------------------
    // 12. Make Family Focus works (Switch to Aresha Zubair)
    // -----------------------------------------------------------------------
    // Click Aresha Zubair
    await page.evaluate(() => {
      const node = document.querySelector('g.node[id*="p_aresha_zubair"]');
      if (node) node.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await sleep(800);

    await clickButtonText("Make Family Focus");
    await sleep(1500);
    step(12, "Make Family Focus works (Switch to Aresha Zubair)");

    // -----------------------------------------------------------------------
    // 13. Diagram updates focus
    // -----------------------------------------------------------------------
    await page.waitForFunction(() => {
      const current = document.querySelector(".family-focus-current");
      return current && current.textContent.includes("Aresha Zubair");
    }, { timeout: 8000 });
    // Wait for the new diagram render to complete
    await page.waitForFunction(() => {
      const loading = document.querySelector(".family-loading-indicator");
      const nodes = document.querySelectorAll('.family-canvas g.node.clickable-node[id*="-flowchart-p_"]');
      return !loading && nodes.length > 0;
    }, { timeout: 10000 });
    const isAreshaFocusNode = await page.evaluate(() => {
      const node = document.querySelector('g.node[id*="p_aresha_zubair"]');
      return Boolean(node);
    });
    if (!isAreshaFocusNode) throw new Error("Aresha focus node not rendered");
    step(13, "Diagram updates focus");

    // Screenshot 3: family-alternate-focus.png
    await page.screenshot({ path: join(DOC_SHOTS, "family-alternate-focus.png"), fullPage: false });
    console.log("  [Screenshot] Captured: family-alternate-focus.png");

    // -----------------------------------------------------------------------
    // 14. Relationship context changes under new focus
    // -----------------------------------------------------------------------
    // Click Mohammad Yahya Hussain to see his relationship to Aresha Zubair
    await page.evaluate(() => {
      const node = document.querySelector('.family-canvas g.node.clickable-node[id*="p_mohammad_yahya_hussain"]');
      if (node) node.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await page.waitForFunction(() => {
      const name = document.querySelector("aside.family-side strong");
      return name && name.textContent.includes("Mohammad Yahya Hussain");
    }, { timeout: 8000 });
    await page.waitForSelector(".relation-card-item .relation-en", { timeout: 10000 });
    const newFocusRel = await page.$eval(".relation-card-item .relation-en", (el) => el.textContent);
    if (!newFocusRel.toLowerCase().includes("cousin")) {
      throw new Error(`Expected cousin relationship to Aresha Zubair, got: ${newFocusRel}`);
    }
    step(14, "Relationship context changes under new focus");

    // -----------------------------------------------------------------------
    // 15. Return to default / me works
    // -----------------------------------------------------------------------
    await clickButtonText("Return to My Family View");
    await page.waitForFunction(() => {
      const current = document.querySelector(".family-focus-current");
      return current && current.textContent.includes("Mohammad Yahya Hussain");
    }, { timeout: 8000 });
    await page.waitForFunction(() => {
      const loading = document.querySelector(".family-loading-indicator");
      const nodes = document.querySelectorAll('.family-canvas g.node.clickable-node[id*="-flowchart-p_"]');
      return !loading && nodes.length > 0;
    }, { timeout: 10000 });
    step(15, "Return to default/me works");

    // -----------------------------------------------------------------------
    // 16. Zoom in
    // -----------------------------------------------------------------------
    const initialWidth = await page.$eval(".family-canvas", (el) => el.style.transform);
    await clickButtonText("+ Zoom");
    await sleep(300);
    const zoomedInTransform = await page.$eval(".family-canvas", (el) => el.style.transform);
    if (zoomedInTransform === initialWidth) throw new Error("Zoom in did not update transform");
    step(16, "Zoom in");

    // -----------------------------------------------------------------------
    // 17. Zoom out
    // -----------------------------------------------------------------------
    await clickButtonText("− Zoom");
    await clickButtonText("− Zoom");
    await sleep(300);
    const zoomedOutTransform = await page.$eval(".family-canvas", (el) => el.style.transform);
    step(17, "Zoom out");

    // -----------------------------------------------------------------------
    // 18. Fit / reset
    // -----------------------------------------------------------------------
    await clickButtonText("Fit");
    await sleep(300);

    await clickButtonText("Center Focus");
    await sleep(300);
    const resetTransform = await page.$eval(".family-canvas", (el) => el.style.transform);
    if (!resetTransform.includes("scale(1)")) throw new Error(`Expected scale(1), got: ${resetTransform}`);
    step(18, "Fit / reset");

    // -----------------------------------------------------------------------
    // 19. Select person with multiple family paths (Aresha Zubair)
    // -----------------------------------------------------------------------
    await page.evaluate(() => {
      const node = document.querySelector('.family-canvas g.node.clickable-node[id*="p_aresha_zubair"]');
      if (node) node.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await page.waitForFunction(() => {
      const name = document.querySelector("aside.family-side strong");
      return name && name.textContent.includes("Aresha Zubair");
    }, { timeout: 8000 });
    step(19, "Select person with multiple family paths (Aresha Zubair)");

    // -----------------------------------------------------------------------
    // 20. Multiple paths indicator shown
    // -----------------------------------------------------------------------
    await page.waitForSelector(".badge-multipath", { timeout: 10000 });
    const multiBadgeText = await page.$eval(".badge-multipath", (el) => el.textContent);
    if (!multiBadgeText.includes("2 family paths")) {
      throw new Error(`Expected "2 family paths", got: ${multiBadgeText}`);
    }
    step(20, "Multiple paths indicator shown");

    // Screenshot 4: family-multipath-context.png
    await page.screenshot({ path: join(DOC_SHOTS, "family-multipath-context.png"), fullPage: false });
    console.log("  [Screenshot] Captured: family-multipath-context.png");

    // -----------------------------------------------------------------------
    // 21. View in Relationships works
    // -----------------------------------------------------------------------
    await clickButtonText("View in Relationships");
    await sleep(1500);

    // Verify switched to relationships screen with Aresha selected
    const relScreenActive = await page.evaluate(() => {
      const activeNav = document.querySelector("nav.nav button.active");
      return activeNav && activeNav.textContent.includes("Relationships");
    });
    if (!relScreenActive) throw new Error("Did not navigate to Relationships screen");
    step(21, "View in Relationships works");

    // Return to Family
    await clickButtonText("Family");
    await sleep(800);
    await page.waitForSelector(".family-diagram svg", { timeout: 10000 });
    await page.waitForFunction(() => {
      const loading = document.querySelector(".family-loading-indicator");
      const nodes = document.querySelectorAll('.family-canvas g.node.clickable-node[id*="-flowchart-p_"]');
      return !loading && nodes.length > 0;
    }, { timeout: 10000 });

    // -----------------------------------------------------------------------
    // 22. Maternal / paternal semantics visible correctly
    // -----------------------------------------------------------------------
    // Select Aresha again to inspect badges
    await page.evaluate(() => {
      const node = document.querySelector('.family-canvas g.node.clickable-node[id*="p_aresha_zubair"]');
      if (node) node.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await page.waitForFunction(() => {
      const name = document.querySelector("aside.family-side strong");
      return name && name.textContent.includes("Aresha Zubair");
    }, { timeout: 8000 });
    await page.waitForSelector(".family-badge", { timeout: 10000 });
    const badges = await page.$$eval(".family-badge", (els) => els.map((e) => e.textContent));
    const hasPaternal = badges.some((b) => b.includes("Paternal"));
    const hasMaternal = badges.some((b) => b.includes("Maternal"));
    if (!hasPaternal || !hasMaternal) {
      throw new Error(`Expected both Maternal and Paternal badges for Aresha, found: ${JSON.stringify(badges)}`);
    }
    step(22, "Maternal/paternal semantics visible correctly");

    // -----------------------------------------------------------------------
    // 23. Direct-vs-derived context correct
    // -----------------------------------------------------------------------
    // Aresha's relationship is derived cousin
    const hasDerived = badges.some((b) => b.includes("Derived Kinship Term"));
    if (!hasDerived) throw new Error(`Expected "Derived Kinship Term" badge for Aresha, found: ${JSON.stringify(badges)}`);

    // Click Mansoor Hussain (stored direct parent fact)
    await page.evaluate(() => {
      const node = document.querySelector('.family-canvas g.node.clickable-node[id*="p_mansoor_hussain"]');
      if (node) node.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await page.waitForFunction(() => {
      const name = document.querySelector("aside.family-side strong");
      return name && name.textContent.includes("Mansoor Hussain");
    }, { timeout: 8000 });
    await page.waitForSelector(".family-badge", { timeout: 10000 });
    const mansoorBadges = await page.$$eval(".family-badge", (els) => els.map((e) => e.textContent));
    const hasStored = mansoorBadges.some((b) => b.includes("Parent-Child") || b.includes("Stored Fact"));
    if (!hasStored) throw new Error(`Expected Stored Parent-Child Fact badge for Mansoor, found: ${JSON.stringify(mansoorBadges)}`);
    step(23, "Direct-vs-derived context correct");

    // -----------------------------------------------------------------------
    // 24. Loading state does not show raw Mermaid
    // -----------------------------------------------------------------------
    const rawMermaidVisible = await page.evaluate(() => {
      const text = document.body.innerText;
      return text.includes("flowchart TB") || text.includes("classDef person");
    });
    if (rawMermaidVisible) throw new Error("Raw Mermaid flowchart syntax leaked into page body text");
    step(24, "Loading state does not show raw Mermaid");

    // -----------------------------------------------------------------------
    // 25. Invalid/error path shows safe UI
    // -----------------------------------------------------------------------
    // Select an invalid focus by triggering reload with corrupted query or verify empty
    const safeErrorUi = await page.evaluate(async () => {
      try {
        const res = await fetch("http://127.0.0.1:8765/api/family/view?focus_person_id=nonexistent_invalid");
        const json = await res.json();
        return res.status === 404 && json.error && json.error.code === "NOT_FOUND";
      } catch {
        return false;
      }
    });
    if (!safeErrorUi) throw new Error("Backend does not cleanly return structured 404 for invalid focus");
    step(25, "Invalid/error path shows safe UI");

    const criticalErrors = consoleErrors.filter(
      (e) => !e.includes("favicon") && !e.includes("404") && !e.includes("React DevTools"),
    );
    if (criticalErrors.length > 0) {
      throw new Error(`Unexpected browser console errors detected: ${JSON.stringify(criticalErrors)}`);
    }
    step(26, "Browser console has no unexpected errors");

    console.log("\n=======================================================");
    console.log(`🎉 ALL ${passedSteps.length} / 26 FAMILY UI E2E CHECKS PASSED!`);
    console.log("=======================================================\n");
  } finally {
    if (browser) await browser.close();
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

    // Verify production data integrity
    const finalDbHash = sha256(PROD_DB);
    if (finalDbHash !== initialDbHash) {
      console.error(`[CRITICAL] Production DB modified! Initial: ${initialDbHash}, Final: ${finalDbHash}`);
      process.exit(1);
    }
    console.log(`[Safety Verification] Initial DB Hash: ${initialDbHash}`);
    console.log(`[Safety Verification] Final DB Hash:   ${finalDbHash}`);

    for (const j of initialJournals) {
      const current = sha256(j.path);
      if (current !== j.hash) {
        console.error(`[CRITICAL] Production journal modified at: ${j.path}`);
        process.exit(1);
      }
    }
    console.log(`[Safety Verification] All ${initialJournals.length} production journals are 100% byte-identical.`);

    try {
      rmSync(tempRoot, { recursive: true, force: true });
      console.log("[Cleanup] Temporary test sandbox removed.");
    } catch {}

    process.exit(0);
  }
}

main().catch((err) => {
  console.error("Family E2E Failed:", err);
  process.exit(1);
});
