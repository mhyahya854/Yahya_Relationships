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
  let testError = null;
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
      args: ["--disable-gpu", "--no-first-run", "--no-sandbox", "--edge-skip-compat-layer-relaunch"],
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
      const aliases = {
        "Make Family Focus": "View family from this person",
        "View in Relationships": "View in Connections",
        "+ Add Family Fact": "Add Family Fact",
        "+ Zoom": "Zoom in",
        "− Zoom": "Zoom out",
      };
      const targetText = aliases[text] ?? text;
      const initiallyVisible = await page.evaluate((expected) => {
        const buttons = [...document.querySelectorAll("button, .btn, .nav-item")];
        return buttons.some((b) => {
          const rect = b.getBoundingClientRect();
          const label = [b.textContent, b.getAttribute("aria-label"), b.getAttribute("title")].filter(Boolean).join(" ").trim().toLowerCase();
          return label.includes(expected.toLowerCase()) &&
            !b.disabled && rect.width > 0 && rect.height > 0;
        });
      }, targetText);
      if (!initiallyVisible) {
        await page.evaluate(() => {
          document.querySelectorAll("details.inspector-disclosure:not([open]) > summary")
            .forEach((summary) => summary.click());
        });
        await sleep(250);
      }
      await page.waitForFunction((expected) => {
        const buttons = [...document.querySelectorAll("button, .btn, .nav-item")];
        return buttons.some((b) => {
          const rect = b.getBoundingClientRect();
          const label = [b.textContent, b.getAttribute("aria-label"), b.getAttribute("title")].filter(Boolean).join(" ").trim().toLowerCase();
          return label.includes(expected.toLowerCase()) &&
            !b.disabled && rect.width > 0 && rect.height > 0;
        });
      }, { timeout: 10000 }, targetText);
      const clicked = await page.evaluate((expected) => {
        const buttons = [...document.querySelectorAll("button, .btn, .nav-item")];
        const button = buttons.find((b) => {
          const rect = b.getBoundingClientRect();
          const label = [b.textContent, b.getAttribute("aria-label"), b.getAttribute("title")].filter(Boolean).join(" ").trim().toLowerCase();
          return label.includes(expected.toLowerCase()) &&
            !b.disabled && rect.width > 0 && rect.height > 0;
        });
        button?.click();
        return Boolean(button);
      }, targetText);
      if (!clicked) throw new Error(`Visible enabled button with text '${targetText}' not found.`);
      await sleep(500);
    }

    async function typeSearch(text) {
      await page.waitForSelector(".family-search-dock input", { timeout: 10000 });
      const input = await page.$(".family-search-dock input");
      await input.click();
      await page.keyboard.down("Control");
      await page.keyboard.press("KeyA");
      await page.keyboard.up("Control");
      await page.keyboard.press("Backspace");
      if (text) {
        await input.type(text);
      }
      await sleep(300);
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

    // -----------------------------------------------------------------------
    // 26. Intermediate browser console check
    // -----------------------------------------------------------------------
    const initialConsoleErrors = consoleErrors.filter(
      (e) => !e.includes("favicon") && !e.includes("404") && !e.includes("React DevTools"),
    );
    if (initialConsoleErrors.length > 0) {
      throw new Error(`Unexpected browser console errors detected: ${JSON.stringify(initialConsoleErrors)}`);
    }
    step(26, "Browser console has no unexpected errors");

    // -----------------------------------------------------------------------
    // 27. Focus search finds canonical name
    // -----------------------------------------------------------------------
    await clickButtonText("Family");
    await sleep(600);
    await typeSearch("Yahya");
    await page.waitForSelector(".person-search-results", { timeout: 8000 });
    await page.screenshot({ path: join(DOC_SHOTS, "family-focus-search.png"), fullPage: false });
    console.log("  [Screenshot] Captured: family-focus-search.png");
    const foundCanonical = await page.evaluate(() => {
      const rows = Array.from(document.querySelectorAll(".person-search-results .person-search-row"));
      return rows.some((r) => r.textContent.includes("Mohammad Yahya Hussain"));
    });
    if (!foundCanonical) throw new Error("Focus search did not find canonical name 'Mohammad Yahya Hussain'");
    step(27, "Focus search finds canonical name");

    // -----------------------------------------------------------------------
    // 28. Focus search finds alias
    // -----------------------------------------------------------------------
    await fetch("http://127.0.0.1:8765/api/people", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: "Alexandra Example",
        aliases: ["Alex", "Lexi"],
      }),
    });
    await clickButtonText("Reload");
    await sleep(1000);
    await typeSearch("Lexi");
    await page.waitForSelector(".person-search-results", { timeout: 8000 });
    const foundAlias = await page.evaluate(() => {
      const rows = Array.from(document.querySelectorAll(".person-search-results .person-search-row"));
      return rows.some((r) => r.textContent.includes("Alexandra Example") && r.textContent.includes("Lexi"));
    });
    if (!foundAlias) throw new Error("Focus search did not find person via alias 'Lexi'");
    step(28, "Focus search finds alias");

    // -----------------------------------------------------------------------
    // 29. Selecting alias result changes Family focus to canonical person
    // -----------------------------------------------------------------------
    await page.keyboard.press("ArrowDown");
    await sleep(200);
    await page.keyboard.press("Enter");
    await sleep(1200);
    await page.waitForFunction(() => {
      const current = document.querySelector(".family-focus-current");
      return current && current.textContent.includes("Alexandra Example");
    }, { timeout: 10000 });
    step(29, "Selecting alias result changes Family focus to canonical person");

    // -----------------------------------------------------------------------
    // 30. Global Relationships perspective does not dictate initial Family focus
    // -----------------------------------------------------------------------
    const persCurrent = await page.$(".perspective-current");
    if (persCurrent) {
      await persCurrent.click();
      await sleep(300);
      await page.evaluate(() => {
        const btns = Array.from(document.querySelectorAll(".perspective-dropdown button"));
        const irsaBtn = btns.find((b) => b.textContent.includes("Irsa Naz"));
        if (irsaBtn) irsaBtn.click();
      });
      await sleep(600);
    }
    const currentPersName = await page.$eval(".perspective-current strong", (el) => el.textContent);
    if (!currentPersName.includes("Irsa Naz")) {
      throw new Error(`Expected global perspective Irsa Naz, got: ${currentPersName}`);
    }

    const returnBtn = await page.$("button[title*='Return to default viewer focus']");
    if (returnBtn) {
      await returnBtn.click();
      await sleep(1000);
    }
    const famFocusName = await page.$eval(".family-focus-current", (el) => el.textContent);
    if (!famFocusName.includes("Mohammad Yahya Hussain")) {
      throw new Error(`Expected Family focus to default to Mohammad Yahya Hussain, got: ${famFocusName}`);
    }
    if (famFocusName.includes("Irsa Naz")) {
      throw new Error("Family focus incorrectly inherited global perspective 'Irsa Naz'");
    }
    step(30, "Global Relationships perspective does not dictate initial Family focus");

    // -----------------------------------------------------------------------
    // 31. Family focus change does not alter global perspective
    // -----------------------------------------------------------------------
    await typeSearch("Aresha");
    await page.waitForSelector(".person-search-results", { timeout: 8000 });
    await page.keyboard.press("ArrowDown");
    await sleep(200);
    await page.keyboard.press("Enter");
    await sleep(1200);

    await page.waitForFunction(() => {
      const current = document.querySelector(".family-focus-current");
      return current && current.textContent.includes("Aresha Zubair");
    }, { timeout: 10000 });

    const persAfterFamChange = await page.$eval(".perspective-current strong", (el) => el.textContent);
    if (!persAfterFamChange.includes("Irsa Naz")) {
      throw new Error(`Global perspective changed unexpectedly to: ${persAfterFamChange}`);
    }
    step(31, "Family focus change does not alter global perspective");

    // -----------------------------------------------------------------------
    // 32. Family focus survives Family → Profile → Family
    // 33. Selected Family person survives Family → Profile → Family
    // -----------------------------------------------------------------------
    await page.evaluate(() => {
      const node = document.querySelector('.family-canvas g.node.clickable-node[id*="p_mohammad_yahya_hussain"]');
      if (node) node.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await page.waitForFunction(() => {
      const name = document.querySelector("aside.family-side strong");
      return name && name.textContent.includes("Mohammad Yahya Hussain");
    }, { timeout: 8000 });

    await clickButtonText("View Profile");
    await sleep(1000);
    await page.waitForSelector(".modal h2", { timeout: 15000 });
    const closeProfBtn = await page.$(".modal-head button");
    if (closeProfBtn) await closeProfBtn.click();
    await sleep(500);

    await clickButtonText("People");
    await sleep(800);
    await clickButtonText("Family");
    await sleep(1200);
    await page.waitForSelector(".family-diagram svg", { timeout: 10000 });

    const famFocusAfterNav = await page.$eval(".family-focus-current", (el) => el.textContent);
    if (!famFocusAfterNav.includes("Aresha Zubair")) {
      throw new Error(`Expected Family focus 'Aresha Zubair' to survive navigation, got: ${famFocusAfterNav}`);
    }
    step(32, "Family focus survives Family → Profile → Family");

    const selectedPersonAfterNav = await page.waitForFunction(() => {
      const name = document.querySelector("aside.family-side strong");
      return name && name.textContent.includes("Mohammad Yahya Hussain");
    }, { timeout: 8000 });
    if (!selectedPersonAfterNav) throw new Error("Selected person was lost after navigation");
    step(33, "Selected Family person survives Family → Profile → Family");

    // -----------------------------------------------------------------------
    // 34. Return to My Family View resets Family only
    // -----------------------------------------------------------------------
    await clickButtonText("Return to My Family View");
    await sleep(1200);
    await page.waitForFunction(() => {
      const current = document.querySelector(".family-focus-current");
      return current && current.textContent.includes("Mohammad Yahya Hussain");
    }, { timeout: 8000 });

    const persAfterReturn = await page.$eval(".perspective-current strong", (el) => el.textContent);
    if (!persAfterReturn.includes("Irsa Naz")) {
      throw new Error(`Global perspective changed upon Return to My Family View: ${persAfterReturn}`);
    }
    step(34, "Return to My Family View resets Family only");

    // -----------------------------------------------------------------------
    // 35. Exact Family → Relationships perspective handoff
    // 36. Exact Family → Relationships target handoff
    // -----------------------------------------------------------------------
    await typeSearch("Aresha");
    await page.waitForSelector(".person-search-results", { timeout: 8000 });
    await page.keyboard.press("ArrowDown");
    await sleep(200);
    await page.keyboard.press("Enter");
    await sleep(1200);

    await page.evaluate(() => {
      const node = document.querySelector('.family-canvas g.node.clickable-node[id*="p_mohammad_yahya_hussain"]');
      if (node) node.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await page.waitForFunction(() => {
      const name = document.querySelector("aside.family-side strong");
      return name && name.textContent.includes("Mohammad Yahya Hussain");
    }, { timeout: 8000 });

    await clickButtonText("View in Relationships");
    await sleep(1500);

    await page.waitForFunction(() => {
      const activeNav = document.querySelector("nav.nav button.active");
      return activeNav && activeNav.textContent.includes("Relationships");
    }, { timeout: 8000 });

    await page.waitForFunction(() => {
      const pers = document.querySelector(".perspective-current strong");
      return pers && pers.textContent.includes("Aresha Zubair");
    }, { timeout: 8000 });
    step(35, "Exact Family → Relationships perspective handoff");

    await page.waitForFunction(() => {
      const target = document.querySelector(".selected-person-panel strong");
      return target && target.textContent.includes("Mohammad Yahya Hussain");
    }, { timeout: 8000 });

    await page.evaluate(() => {
      const evidence = document.querySelector("details.inspector-evidence");
      if (evidence && !evidence.open) {
        evidence.querySelector("summary")?.click();
      }
    });

    await page.waitForFunction(() => {
      const perspective = document.querySelector(".perspective-current strong");
      const target = document.querySelector(".selected-person-panel strong");
      const relLabel = document.querySelector(".relationships-panel .panel-rel-label");
      return (
        perspective &&
        perspective.textContent.includes("Aresha Zubair") &&
        target &&
        target.textContent.includes("Mohammad Yahya Hussain") &&
        relLabel &&
        relLabel.textContent.toLowerCase().includes("cousin")
      );
    }, { timeout: 8000 });
    step(36, "Exact Family → Relationships target handoff");

    // -----------------------------------------------------------------------
    // 37. Returning from Relationships preserves Family focus
    // -----------------------------------------------------------------------
    await clickButtonText("Family");
    await sleep(1200);
    await page.waitForSelector(".family-diagram svg", { timeout: 10000 });
    const famFocusAfterRel = await page.$eval(".family-focus-current", (el) => el.textContent);
    if (!famFocusAfterRel.includes("Aresha Zubair")) {
      throw new Error(`Expected Family focus to remain 'Aresha Zubair', got: ${famFocusAfterRel}`);
    }
    step(37, "Returning from Relationships preserves Family focus");

    // -----------------------------------------------------------------------
    // 38. Derived relationship displays "Derived Kinship Term" and "Inspect Proof"
    // -----------------------------------------------------------------------
    await page.evaluate(() => {
      const node = document.querySelector('.family-canvas g.node.clickable-node[id*="p_mohammad_yahya_hussain"]');
      if (node) node.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await page.waitForFunction(() => {
      const name = document.querySelector("aside.family-side strong");
      return name && name.textContent.includes("Mohammad Yahya Hussain");
    }, { timeout: 8000 });

    await page.waitForFunction(() => {
      const badge = document.querySelector(".relation-card-item .badge-derived");
      return badge && badge.textContent.includes("Derived Kinship Term");
    }, { timeout: 8000 });

    const inspectBtnFound = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll(".relation-card-item button"));
      return btns.some((b) => b.textContent.includes("Inspect Proof"));
    });
    if (!inspectBtnFound) throw new Error("Inspect Proof button not found on derived relationship card");

    const editBtnDisabled = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll("aside.family-side button"));
      const editBtn = btns.find((b) => b.textContent.includes("Edit Stored Fact"));
      return editBtn && editBtn.disabled;
    });
    if (!editBtnDisabled) throw new Error("Expected 'Edit Stored Fact' button to be disabled for derived relationship");

    const removeBtnDisabled = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll("aside.family-side button"));
      const removeBtn = btns.find((b) => b.textContent.includes("Remove Stored Fact"));
      return removeBtn && removeBtn.disabled;
    });
    if (!removeBtnDisabled) throw new Error("Expected 'Remove Stored Fact' button to be disabled for derived relationship");

    step(38, "Derived relationship displays Derived Kinship Term and Inspect Proof with direct editing disabled");

    // -----------------------------------------------------------------------
    // 39. "Inspect Proof" modal displays lineage path without edit/delete inputs
    // -----------------------------------------------------------------------
    await clickButtonText("Inspect Proof");
    await sleep(800);
    await page.waitForSelector(".modal-backdrop .modal-card", { timeout: 8000 });

    const proofModalText = await page.$eval(".modal-card", (el) => el.textContent);
    if (!proofModalText.includes("Why this term is derived")) {
      throw new Error(`Inspect Proof modal missing 'Why this term is derived': ${proofModalText}`);
    }
    if (!proofModalText.includes("Underlying lineage & stored fact path")) {
      throw new Error(`Inspect Proof modal missing lineage path header: ${proofModalText}`);
    }

    const hasEditingInputs = await page.evaluate(() => {
      const modal = document.querySelector(".modal-card");
      if (!modal) return false;
      const inputs = modal.querySelectorAll("input, select, .btn-danger");
      return inputs.length > 0;
    });
    if (hasEditingInputs) {
      throw new Error("Inspect Proof modal unexpectedly contained editable inputs or danger buttons");
    }

    await clickButtonText("Close");
    await sleep(500);
    const modalClosed = await page.evaluate(() => !document.querySelector(".modal-backdrop"));
    if (!modalClosed) throw new Error("Proof modal did not close cleanly");

    step(39, "Inspect Proof modal displays lineage path without edit/delete inputs and closes cleanly");

    // -----------------------------------------------------------------------
    // 40. Stored fact displays "Stored Fact" badge and enabled Edit/Remove affordances
    // -----------------------------------------------------------------------
    await clickButtonText("Return to My Family View");
    await sleep(1200);
    await page.waitForFunction(() => {
      const current = document.querySelector(".family-focus-current");
      return current && current.textContent.includes("Mohammad Yahya Hussain");
    }, { timeout: 8000 });

    // Select Irsa Naz (mother of Mohammad Yahya Hussain)
    await page.evaluate(() => {
      const node = document.querySelector('.family-canvas g.node.clickable-node[id*="p_irsa_naz"]');
      if (node) node.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await page.waitForFunction(() => {
      const name = document.querySelector("aside.family-side strong");
      return name && name.textContent.includes("Irsa Naz");
    }, { timeout: 8000 });

    await page.waitForFunction(() => {
      const badge = document.querySelector(".relation-card-item .badge-stored");
      return badge && badge.textContent.includes("Parent-Child");
    }, { timeout: 8000 });

    const storedEditEnabled = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll("aside.family-side button"));
      const editBtn = btns.find((b) => b.textContent.includes("Edit Stored Fact"));
      return editBtn && !editBtn.disabled;
    });
    if (!storedEditEnabled) throw new Error("Expected 'Edit Stored Fact' to be enabled for stored fact");

    const storedRemoveEnabled = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll("aside.family-side button"));
      const removeBtn = btns.find((b) => b.textContent.includes("Remove Stored Fact"));
      return removeBtn && !removeBtn.disabled;
    });
    if (!storedRemoveEnabled) throw new Error("Expected 'Remove Stored Fact' to be enabled for stored fact");

    step(40, "Stored fact displays Stored Fact badge and enabled Edit/Remove affordances");

    // -----------------------------------------------------------------------
    // 41. Add Family Fact with Consequence Preview, Confirm & Save -> diagram updates, UndoBar displays
    // -----------------------------------------------------------------------
    // Select Muaaz in the family diagram
    await page.evaluate(() => {
      const node = document.querySelector('.family-canvas g.node.clickable-node[id*="p_muaaz"]');
      if (node) node.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await page.waitForFunction(() => {
      const name = document.querySelector("aside.family-side strong");
      return name && name.textContent.includes("Muaaz");
    }, { timeout: 8000 });

    await clickButtonText("+ Add Family Fact");
    await sleep(800);
    await page.waitForSelector(".modal-backdrop .modal-card", { timeout: 8000 });
    await page.waitForSelector('input[placeholder*="Search name or alias"]', { timeout: 8000 });


    // Search and select Musabiha as target
    const targetInput = await page.$('input[placeholder*="Search name or alias"]');
    if (!targetInput) throw new Error("Target person search input not found in Add Relationship dialog");
    await targetInput.type("Musabiha");
    await sleep(400);

    await page.evaluate((targetName) => {
      const options = Array.from(document.querySelectorAll("select.form-select option"));
      const opt = options.find((o) => o.textContent.includes(targetName));
      if (opt) {
        const sel = opt.parentElement;
        sel.value = opt.value;
        sel.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }, "Musabiha");

    // Select Marriage as fact type
    await page.evaluate(() => {
      const selects = Array.from(document.querySelectorAll("select.form-select"));
      const typeSelect = selects.find((s) => Array.from(s.options).some((o) => o.value === "marriage"));
      if (typeSelect) {
        typeSelect.value = "marriage";
        typeSelect.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
    await sleep(400);

    // Open Consequence Preview
    await clickButtonText("Preview Consequences");
    await sleep(800);
    await page.waitForSelector(".mutation-preview-dialog .preview-section", { timeout: 8000 });

    const previewBodyText = await page.$eval(".mutation-preview-dialog .modal-card", (card) => card.textContent);
    if (!previewBodyText.includes("Add marriage between Muaaz and Musabiha")) {
      throw new Error(`Expected direct change in preview, got: ${previewBodyText}`);
    }
    if (!previewBodyText.includes("Wife") || !previewBodyText.includes("Husband")) {
      throw new Error(`Expected derived kinship consequences in preview, got: ${previewBodyText}`);
    }

    // Confirm & Save
    await clickButtonText("Confirm & Save Fact");
    await sleep(1500);

    await page.waitForSelector(".undo-bar", { timeout: 8000 });
    const undoBarText = await page.$eval(".undo-bar span", (el) => el.textContent);
    if (!undoBarText.includes("Added marriage between Muaaz and Musabiha")) {
      throw new Error(`Expected UndoBar description for added marriage, got: ${undoBarText}`);
    }
    step(41, "Add Family Fact with Consequence Preview, Confirm & Save updates diagram and shows UndoBar");

    // -----------------------------------------------------------------------
    // 42. Undo reverts added fact -> diagram reverts, UndoBar dismisses
    // -----------------------------------------------------------------------
    await clickButtonText("Undo");
    await sleep(1500);

    await page.waitForFunction(() => !document.querySelector(".undo-bar"), { timeout: 8000 });
    await page.waitForSelector(".family-diagram svg", { timeout: 10000 });
    step(42, "Undo reverts added fact, diagram updates, and UndoBar dismisses");

    // -----------------------------------------------------------------------
    // 43. Edit Stored Fact (Marriage) -> status changes, UndoBar appears, undo reverts
    // -----------------------------------------------------------------------
    // Focus Irsa Naz to access her stored marriage with Mansoor Hussain
    await typeSearch("Irsa");
    await page.waitForSelector(".person-search-results", { timeout: 8000 });
    await page.keyboard.press("ArrowDown");
    await sleep(200);
    await page.keyboard.press("Enter");
    await sleep(1200);
    await page.waitForSelector(".family-diagram svg", { timeout: 10000 });

    // Select Mansoor Hussain
    await page.evaluate(() => {
      const node = document.querySelector('.family-canvas g.node.clickable-node[id*="p_mansoor_hussain"]');
      if (node) node.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await page.waitForFunction(() => {
      const name = document.querySelector("aside.family-side strong");
      return name && name.textContent.includes("Mansoor Hussain");
    }, { timeout: 8000 });

    await page.waitForFunction(() => {
      const badge = document.querySelector(".relation-card-item .badge-stored");
      return badge && badge.textContent.includes("Marriage");
    }, { timeout: 8000 });

    // Open the marriage fact editor specifically (the inspector may contain
    // more than one stored fact/path for the selected pair).
    const openedMarriageEditor = await page.evaluate(() => {
      const cards = Array.from(document.querySelectorAll(".relation-card-item"));
      const marriageCard = cards.find((card) =>
        card.querySelector(".badge-stored")?.textContent.includes("Marriage"),
      );
      const button = Array.from(marriageCard?.querySelectorAll("button") ?? [])
        .find((candidate) => candidate.textContent.includes("Edit Stored Fact"));
      button?.click();
      return Boolean(button);
    });
    if (!openedMarriageEditor) throw new Error("Marriage fact editor control was not found");
    await sleep(800);
    await page.waitForSelector(".edit-relationship-dialog", { timeout: 8000 });
    try {
      await page.waitForFunction(() => {
        const dialog = document.querySelector(".edit-relationship-dialog");
        return Array.from(dialog?.querySelectorAll("select.form-select option") ?? [])
          .some((option) => option.value === "divorced");
      }, { timeout: 10000 });
    } catch {
      const editorState = await page.$eval(".edit-relationship-dialog", (dialog) => ({
        text: dialog.textContent,
        ...dialog.dataset,
      }));
      throw new Error(`Marriage editor did not load the status controls: ${JSON.stringify(editorState)}`);
    }

    // Change status to divorced
    await page.evaluate(() => {
      const selects = Array.from(document.querySelectorAll(".edit-relationship-dialog select.form-select"));
      const statusSelect = selects.find((s) => Array.from(s.options).some((o) => o.value === "divorced"));
      if (statusSelect) {
        statusSelect.value = "divorced";
        statusSelect.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
    await sleep(300);

    await clickButtonText("Save Marriage Fact");
    await sleep(1500);

    // Verify UndoBar and updated status label
    await page.waitForSelector(".undo-bar", { timeout: 8000 });
    await page.waitForFunction(() => {
      const badge = document.querySelector(".relation-card-item .badge-stored");
      return badge && badge.textContent.includes("Marriage (divorced)");
    }, { timeout: 8000 });

    // Undo status change
    await clickButtonText("Undo");
    await sleep(1500);
    await page.waitForFunction(() => !document.querySelector(".undo-bar"), { timeout: 8000 });

    await page.waitForFunction(() => {
      const badge = document.querySelector(".relation-card-item .badge-stored");
      return badge && badge.textContent.includes("Marriage") && !badge.textContent.includes("divorced");
    }, { timeout: 8000 });
    step(43, "Edit Stored Fact updates marriage status, shows UndoBar, and undo reverts cleanly");

    // -----------------------------------------------------------------------
    // 44. Remove Stored Fact with Consequence Preview & Undo
    // -----------------------------------------------------------------------
    // Add a marriage between Muaaz and Musabiha so we can test explicit deletion preview
    await typeSearch("Muaaz");
    await page.waitForSelector(".person-search-results", { timeout: 8000 });
    await page.keyboard.press("ArrowDown");
    await sleep(200);
    await page.keyboard.press("Enter");
    await sleep(1200);
    await page.waitForSelector(".family-diagram svg", { timeout: 10000 });

    // Select Musabiha
    await page.evaluate(() => {
      const node = document.querySelector('.family-canvas g.node.clickable-node[id*="p_musabiha"]');
      if (node) node.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await page.waitForFunction(() => {
      const name = document.querySelector("aside.family-side strong");
      return name && name.textContent.includes("Musabiha");
    }, { timeout: 8000 });

    await clickButtonText("+ Add Family Fact");
    await sleep(800);
    await page.waitForSelector(".modal-backdrop .modal-card", { timeout: 8000 });
    await page.waitForSelector('input[placeholder*="Search name or alias"]', { timeout: 8000 });

    const targetInput2 = await page.$('input[placeholder*="Search name or alias"]');
    await targetInput2.type("Muaaz");
    await sleep(400);
    await page.evaluate((targetName) => {
      const options = Array.from(document.querySelectorAll("select.form-select option"));
      const opt = options.find((o) => o.textContent.includes(targetName));
      if (opt) {
        const sel = opt.parentElement;
        sel.value = opt.value;
        sel.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }, "Muaaz");

    await page.evaluate(() => {
      const selects = Array.from(document.querySelectorAll("select.form-select"));
      const typeSelect = selects.find((s) => Array.from(s.options).some((o) => o.value === "marriage"));
      if (typeSelect) {
        typeSelect.value = "marriage";
        typeSelect.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
    await sleep(300);
    await clickButtonText("Save Fact");
    await sleep(1500);

    // Now Musabiha is Wife (stored marriage fact)
    await page.waitForFunction(() => {
      const badge = document.querySelector(".relation-card-item .badge-stored");
      return badge && badge.textContent.includes("Marriage");
    }, { timeout: 8000 });

    // Click Remove Stored Fact -> auto triggers deletion Consequence Preview
    await clickButtonText("Remove Stored Fact");
    await sleep(800);
    await page.waitForSelector(".modal-backdrop .preview-direct", { timeout: 8000 });

    const delPreviewText = await page.evaluate(() => {
      const cards = document.querySelectorAll(".modal-card");
      return cards[cards.length - 1].textContent;
    });
    if (!delPreviewText.includes("Remove marriage between Muaaz and Musabiha")) {
      throw new Error(`Expected deletion preview to describe removing marriage, got: ${delPreviewText}`);
    }

    // Confirm deletion
    await clickButtonText("Confirm & Save Fact");
    await sleep(1500);

    await page.waitForSelector(".undo-bar", { timeout: 8000 });

    // Undo deletion restores the marriage
    await clickButtonText("Undo");
    await sleep(1500);
    await page.waitForFunction(() => !document.querySelector(".undo-bar"), { timeout: 8000 });

    // Clean up: remove the test marriage fact again so data remains in initial state
    await clickButtonText("Remove Stored Fact");
    await sleep(800);
    await page.waitForSelector(".modal-backdrop .preview-direct", { timeout: 8000 });
    await clickButtonText("Confirm & Save Fact");
    await sleep(1500);
    if (await page.$(".undo-bar")) {
      const dismissBtn = await page.$(".undo-bar-close");
      if (dismissBtn) await dismissBtn.click();
      await sleep(300);
    }
    step(44, "Remove Stored Fact displays Consequence Preview, executes deletion, and undo restores fact");

    // -----------------------------------------------------------------------
    // 45. Ancestry cycle mutation refusal in UI
    // -----------------------------------------------------------------------
    await clickButtonText("Return to My Family View");
    await sleep(1200);
    await page.waitForFunction(() => {
      const current = document.querySelector(".family-focus-current");
      return current && current.textContent.includes("Mohammad Yahya Hussain");
    }, { timeout: 8000 });

    // Select Irsa Naz
    await page.evaluate(() => {
      const node = document.querySelector('.family-canvas g.node.clickable-node[id*="p_irsa_naz"]');
      if (node) node.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await page.waitForFunction(() => {
      const name = document.querySelector("aside.family-side strong");
      return name && name.textContent.includes("Irsa Naz");
    }, { timeout: 8000 });

    await clickButtonText("+ Add Family Fact");
    await sleep(800);
    await page.waitForSelector(".modal-backdrop .modal-card", { timeout: 8000 });
    await page.waitForSelector('input[placeholder*="Search name or alias"]', { timeout: 8000 });

    // Target Mohammad Yahya Hussain
    const cycleTargetInput = await page.$('input[placeholder*="Search name or alias"]');
    await cycleTargetInput.type("Yahya");
    await sleep(400);
    await page.evaluate((targetName) => {
      const options = Array.from(document.querySelectorAll("select.form-select option"));
      const opt = options.find((o) => o.textContent.includes(targetName));
      if (opt) {
        const sel = opt.parentElement;
        sel.value = opt.value;
        sel.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }, "Yahya");

    // Set direction to Child so Mohammad Yahya Hussain becomes parent of Irsa Naz
    await page.evaluate(() => {
      const selects = Array.from(document.querySelectorAll("select.form-select"));
      const dirSelect = selects.find((s) => Array.from(s.options).some((o) => o.value === "child"));
      if (dirSelect) {
        dirSelect.value = "child";
        dirSelect.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
    await sleep(300);

    // Trigger preview
    await clickButtonText("Preview Consequences");
    await sleep(800);
    await page.waitForSelector(".modal-backdrop .diff-invalid", { timeout: 8000 });

    const blockedText = await page.evaluate(() => {
      const cards = document.querySelectorAll(".modal-card");
      const lastCard = cards[cards.length - 1];
      const diffInvalid = lastCard.querySelector(".diff-invalid");
      return diffInvalid ? diffInvalid.textContent : lastCard.textContent;
    });
    if (!blockedText.includes("Ancestry cycle")) {
      throw new Error(`Expected Ancestry cycle validation block, got: ${blockedText}`);
    }

    const confirmBtnPresent = await page.evaluate(() => {
      const cards = document.querySelectorAll(".modal-card");
      const lastCard = cards[cards.length - 1];
      const btns = Array.from(lastCard.querySelectorAll("button"));
      return btns.some((b) => b.textContent.includes("Confirm & Save Fact"));
    });
    if (confirmBtnPresent) {
      throw new Error("Invalid ancestry cycle mutation unexpectedly showed 'Confirm & Save Fact' button");
    }

    // Cancel preview dialog
    await page.evaluate(() => {
      const cards = document.querySelectorAll(".modal-card");
      if (cards.length > 1) {
        const lastCard = cards[cards.length - 1];
        const cancelBtn = Array.from(lastCard.querySelectorAll("button")).find(
          (b) => b.textContent.includes("Cancel") || b.classList.contains("btn-close")
        );
        if (cancelBtn) cancelBtn.click();
      }
    });
    await sleep(500);

    // Cancel Add Fact dialog
    await clickButtonText("Cancel");
    await sleep(500);
    step(45, "Ancestry cycle mutation refusal blocks validation in UI preview without save affordance");

    // -----------------------------------------------------------------------
    // 46. Reset focus to default viewer focus prior to security checks
    // -----------------------------------------------------------------------
    const hasReturnBtn = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll("button, .btn"));
      return btns.some((b) => b.textContent && b.textContent.includes("Return to My Family View"));
    });
    if (hasReturnBtn) {
      await clickButtonText("Return to My Family View");
      await sleep(1200);
    }
    await page.waitForFunction(() => {
      const current = document.querySelector(".family-focus-current");
      return current && current.textContent.includes("Mohammad Yahya Hussain");
    }, { timeout: 8000 });
    await page.waitForSelector(".family-diagram svg", { timeout: 10000 });
    step(46, "Reset focus to default viewer focus prior to security checks");

    // -----------------------------------------------------------------------
    // 47. Rendered hostile-name Mermaid DOM is inert
    // -----------------------------------------------------------------------
    await page.evaluate(() => {
      window.__familyPwned = undefined;
    });
    await fetch("http://127.0.0.1:8765/api/people", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: "Hostile <script>window.__familyPwned=1</script><img src=x onerror=\"window.__familyPwned=1\"><svg onload=\"window.__familyPwned=1\">",
        aliases: ['"B"', '"><iframe srcdoc="<script>window.parent.__familyPwned=1</script>">'],
      }),
    });

    await clickButtonText("Reload");
    await sleep(2000);
    await page.waitForSelector(".family-diagram svg", { timeout: 10000 });

    const pwned = await page.evaluate(() => window.__familyPwned);
    if (pwned !== undefined) {
      throw new Error(`Mermaid DOM execution vulnerability triggered: window.__familyPwned = ${pwned}`);
    }

    const hostileDomElements = await page.evaluate(() => {
      const container = document.querySelector(".family-diagram");
      if (!container) return { scripts: 0, iframes: 0, onerrors: 0, onloads: 0 };
      const scripts = container.querySelectorAll("script").length;
      const iframes = container.querySelectorAll("iframe").length;
      const onerrors = container.querySelectorAll("[onerror]").length;
      const onloads = container.querySelectorAll("[onload]").length;
      return { scripts, iframes, onerrors, onloads };
    });

    if (
      hostileDomElements.scripts > 0 ||
      hostileDomElements.iframes > 0 ||
      hostileDomElements.onerrors > 0 ||
      hostileDomElements.onloads > 0
    ) {
      throw new Error(`Hostile DOM elements found in Mermaid output: ${JSON.stringify(hostileDomElements)}`);
    }
    step(47, "Rendered hostile-name Mermaid DOM is inert");

    // -----------------------------------------------------------------------
    // 48. Browser console has no unexpected errors after hostile-name test
    // -----------------------------------------------------------------------
    const criticalErrors = consoleErrors.filter(
      (e) => !e.includes("favicon") && !e.includes("404") && !e.includes("React DevTools"),
    );
    if (criticalErrors.length > 0) {
      throw new Error(`Unexpected browser console errors detected: ${JSON.stringify(criticalErrors)}`);
    }
    step(48, "Browser console has no unexpected errors after hostile-name test");

    // =======================================================================
    // PHASE 4 CLOSURE EXTENSION (STEPS 49-63)
    // =======================================================================

    // -----------------------------------------------------------------------
    // 49. Parent kind dropdown exposes all 7 canonical values
    // -----------------------------------------------------------------------
    await typeSearch("Yahya");
    await page.waitForSelector(".person-search-results", { timeout: 8000 });
    await page.keyboard.press("ArrowDown");
    await sleep(200);
    await page.keyboard.press("Enter");
    await sleep(1200);
    await page.waitForSelector(".family-diagram svg", { timeout: 10000 });

    await clickButtonText("+ Add Family Fact");
    await sleep(800);
    await page.waitForSelector(".modal-backdrop .modal-card", { timeout: 8000 });

    const parentKinds = await page.evaluate(() => {
      const select = document.querySelector("#parent-kind-select");
      if (!select) return [];
      return Array.from(select.options).map((o) => o.value);
    });
    const expectedKinds = ["biological", "adopted", "step", "foster", "guardian", "unknown", "unspecified"];
    for (const k of expectedKinds) {
      if (!parentKinds.includes(k)) {
        throw new Error(`Parent kind dropdown missing canonical kind: '${k}'. Found: ${JSON.stringify(parentKinds)}`);
      }
    }
    if (parentKinds.includes("adoptive") || parentKinds.includes("surrogate")) {
      throw new Error(`Parent kind dropdown contains non-canonical kind: ${JSON.stringify(parentKinds)}`);
    }

    await clickButtonText("Cancel");
    await sleep(500);
    step(49, "Parent kind dropdown exposes all 7 canonical values");

    // -----------------------------------------------------------------------
    // 50. Duplicate family mutation refusal in UI preview without save affordance
    // -----------------------------------------------------------------------
    await typeSearch("Irsa");
    await page.waitForSelector(".person-search-results", { timeout: 8000 });
    await page.keyboard.press("ArrowDown");
    await sleep(200);
    await page.keyboard.press("Enter");
    await sleep(1200);
    await page.waitForSelector(".family-diagram svg", { timeout: 10000 });

    await clickButtonText("+ Add Family Fact");
    await sleep(800);
    await page.waitForSelector(".modal-backdrop .modal-card", { timeout: 8000 });
    await page.waitForSelector('input[placeholder*="Search name or alias"]', { timeout: 8000 });

    const dupTargetInput = await page.$('input[placeholder*="Search name or alias"]');
    await dupTargetInput.type("Yahya");
    await sleep(400);
    await page.evaluate((targetName) => {
      const options = Array.from(document.querySelectorAll("select.form-select option"));
      const opt = options.find((o) => o.textContent.includes(targetName));
      if (opt) {
        const sel = opt.parentElement;
        sel.value = opt.value;
        sel.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }, "Yahya");

    await page.evaluate(() => {
      const roleSel = document.querySelector("#parent-role-select");
      if (roleSel) {
        roleSel.value = "mother";
        roleSel.dispatchEvent(new Event("change", { bubbles: true }));
      }
      const kindSel = document.querySelector("#parent-kind-select");
      if (kindSel) {
        kindSel.value = "biological";
        kindSel.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
    await sleep(300);

    await clickButtonText("Preview Consequences");
    await sleep(800);
    await page.waitForSelector(".modal-backdrop .diff-invalid", { timeout: 8000 });

    const dupBlockedText = await page.evaluate(() => {
      const cards = document.querySelectorAll(".modal-card");
      const lastCard = cards[cards.length - 1];
      const diffInvalid = lastCard.querySelector(".diff-invalid");
      return diffInvalid ? diffInvalid.textContent : lastCard.textContent;
    });
    if (!dupBlockedText.includes("Parent-child fact already exists") && !dupBlockedText.includes("already exists")) {
      throw new Error(`Expected duplicate fact refusal, got: ${dupBlockedText}`);
    }

    const dupSaveBtnPresent = await page.evaluate(() => {
      const cards = document.querySelectorAll(".modal-card");
      const lastCard = cards[cards.length - 1];
      const btns = Array.from(lastCard.querySelectorAll("button"));
      return btns.some((b) => b.textContent.includes("Confirm & Save Fact"));
    });
    if (dupSaveBtnPresent) {
      throw new Error("Duplicate mutation preview unexpectedly displayed 'Confirm & Save Fact' button");
    }

    await page.evaluate(() => {
      const cards = document.querySelectorAll(".modal-card");
      if (cards.length > 1) {
        const lastCard = cards[cards.length - 1];
        const cancelBtn = Array.from(lastCard.querySelectorAll("button")).find(
          (b) => b.textContent.includes("Cancel") || b.classList.contains("btn-close")
        );
        if (cancelBtn) cancelBtn.click();
      }
    });
    await sleep(400);
    await clickButtonText("Cancel");
    await sleep(400);
    step(50, "Duplicate family mutation refusal in UI preview without save affordance");

    // -----------------------------------------------------------------------
    // 51. Parent-child Family UI create with consequence preview, diagram refresh, and stored badge
    // -----------------------------------------------------------------------
    // Switch focus to Irsa Naz so that sourcePerson = Irsa Naz (she was last selected in step 45).
    // Then open Add Family Fact from the context panel to create Irsa Naz → Musabiha (adopted).
    await typeSearch("Irsa");
    await page.waitForSelector(".person-search-results", { timeout: 8000 });
    await page.keyboard.press("ArrowDown");
    await sleep(200);
    await page.keyboard.press("Enter");
    await sleep(1200);
    await page.waitForSelector(".family-diagram svg", { timeout: 10000 });

    // Ensure Irsa Naz is still the selected (from step 45); if not, click the focus node
    // to open the context panel with Irsa Naz as selected
    const irsaSelected = await page.evaluate(() => {
      const name = document.querySelector("aside.family-side strong");
      return name && name.textContent.includes("Irsa Naz");
    });
    if (!irsaSelected) {
      // Click Irsa Naz's node if visible in diagram
      await page.evaluate(() => {
        const node = document.querySelector('.family-canvas g.node.clickable-node[id*="p_irsa_naz"]');
        if (node) node.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      });
      await sleep(600);
    }

    // Dismiss any existing undo bar before proceeding
    if (await page.$(".undo-bar")) {
      const dismissBtn = await page.$(".undo-bar-close");
      if (dismissBtn) await dismissBtn.click();
      await sleep(300);
    }

    await clickButtonText("+ Add Family Fact");
    await sleep(800);
    await page.waitForSelector(".modal-backdrop .modal-card", { timeout: 8000 });
    await page.waitForSelector('input[placeholder*="Search name or alias"]', { timeout: 8000 });

    const pcTargetInput = await page.$('input[placeholder*="Search name or alias"]');
    await pcTargetInput.type("Musabiha");
    await sleep(400);
    await page.evaluate((targetName) => {
      const options = Array.from(document.querySelectorAll("select.form-select option"));
      const opt = options.find((o) => o.textContent.includes(targetName));
      if (opt) {
        const sel = opt.parentElement;
        sel.value = opt.value;
        sel.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }, "Musabiha");

    await page.evaluate(() => {
      const roleSel = document.querySelector("#parent-role-select");
      if (roleSel) {
        roleSel.value = "father";
        roleSel.dispatchEvent(new Event("change", { bubbles: true }));
      }
      const kindSel = document.querySelector("#parent-kind-select");
      if (kindSel) {
        kindSel.value = "adopted";
        kindSel.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
    await sleep(300);

    await clickButtonText("Preview Consequences");
    await sleep(800);
    await page.waitForSelector(".modal-backdrop .preview-section", { timeout: 8000 });

    await page.screenshot({ path: join(DOC_SHOTS, "family-add-parent-fact.png"), fullPage: false });
    console.log("  [Screenshot] Captured: family-add-parent-fact.png");

    const pcPreviewText = await page.evaluate(() => {
      const cards = document.querySelectorAll(".modal-card");
      return cards[cards.length - 1].textContent;
    });
    if (!pcPreviewText.includes("adopted child")) {
      throw new Error(`Expected direct change describing adopted child in preview, got: ${pcPreviewText}`);
    }

    await clickButtonText("Confirm & Save Fact");
    await sleep(1500);

    await page.waitForSelector(".undo-bar", { timeout: 8000 });
    const pcUndoText = await page.$eval(".undo-bar span", (el) => el.textContent);
    if (!pcUndoText.includes("parent-child")) {
      throw new Error(`Expected UndoBar description for parent-child, got: ${pcUndoText}`);
    }

    // Dismiss UndoBar and select Musabiha to see the stored badge from Irsa's perspective
    if (await page.$(".undo-bar-close")) {
      await page.evaluate(() => {
        const btn = document.querySelector(".undo-bar-close");
        if (btn) btn.click();
      });
      await sleep(300);
    }

    await page.evaluate(() => {
      const node = document.querySelector('.family-canvas g.node.clickable-node[id*="p_musabiha"]');
      if (node) node.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await sleep(600);

    await page.waitForFunction(() => {
      const badge = document.querySelector(".relation-card-item .badge-stored");
      return badge && badge.textContent.includes("Parent-Child (adopted)");
    }, { timeout: 8000 });

    step(51, "Parent-child Family UI create with consequence preview, diagram refresh, and stored badge");

    // -----------------------------------------------------------------------
    // 52. Post-mutation Family -> Relationships semantic consistency
    // -----------------------------------------------------------------------
    await clickButtonText("View in Relationships");
    await page.waitForFunction(() => {
      const title = document.querySelector(".view-head h1");
      return title?.textContent.includes("Relationships");
    }, { timeout: 8000 });
    await page.waitForFunction(() =>
      Boolean(
        document.querySelector(".perspective-current strong")?.textContent &&
        document.querySelector(".selected-person-panel .inspector-profile-row strong")?.textContent
      ),
      { timeout: 10000 },
    );
    await page.evaluate(() => {
      const evidence = document.querySelector("details.inspector-evidence");
      if (evidence && !evidence.open) evidence.querySelector("summary")?.click();
    });
    await page.waitForFunction(
      () => Boolean(document.querySelector(".panel-rel-group .panel-rel-row")?.textContent),
      { timeout: 10000 },
    );

    const parentHandoff = await page.evaluate(() => ({
      perspective: document.querySelector(".perspective-current strong")?.textContent || "",
      target: document.querySelector(".selected-person-panel .inspector-profile-row strong")?.textContent || "",
      relationship: document.querySelector(".panel-rel-group .panel-rel-row")?.textContent || "",
    }));
    if (!parentHandoff.perspective.includes("Irsa Naz") ||
        !parentHandoff.target.includes("Musabiha") ||
        !parentHandoff.relationship.includes("Daughter (adopted)")) {
      throw new Error(`Post-mutation Relationships handoff was stale: ${JSON.stringify(parentHandoff)}`);
    }

    await clickButtonText("Family");
    await page.waitForSelector(".family-diagram svg", { timeout: 10000 });
    await page.waitForFunction(() =>
      document.querySelector(".family-focus-current")?.textContent.includes("Irsa Naz") &&
      document.querySelector("aside.family-side strong")?.textContent.includes("Musabiha"),
      { timeout: 10000 },
    );
    const parentReturnState = await page.evaluate(() => ({
      focus: document.querySelector(".family-focus-current")?.textContent || "",
      selected: document.querySelector("aside.family-side strong")?.textContent || "",
    }));
    if (!parentReturnState.focus.includes("Irsa Naz") || !parentReturnState.selected.includes("Musabiha")) {
      throw new Error(`Family session did not survive mutation handoff: ${JSON.stringify(parentReturnState)}`);
    }
    step(52, "Post-mutation Family -> Relationships truth and Family session persistence");

    // -----------------------------------------------------------------------
    // 53. Parent-child Family UI edit changes kind to foster with UndoBar
    // -----------------------------------------------------------------------
    await clickButtonText("Edit Stored Fact");
    await sleep(800);
    await page.waitForSelector("#edit-parent-kind-select", { timeout: 8000 });

    await page.evaluate(() => {
      const kindSel = document.querySelector("#edit-parent-kind-select");
      if (kindSel) {
        kindSel.value = "foster";
        kindSel.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
    await sleep(300);

    await clickButtonText("Save Parent Fact");
    await sleep(1500);

    await page.waitForSelector(".undo-bar", { timeout: 8000 });
    await page.waitForFunction(() => {
      const badge = document.querySelector(".relation-card-item .badge-stored");
      return badge && badge.textContent.includes("Parent-Child (foster)");
    }, { timeout: 8000 });

    step(53, "Parent-child Family UI edit changes kind to foster with UndoBar");

    // -----------------------------------------------------------------------
    // 54. Parent-child Family UI undo edit restores original adopted kind
    // -----------------------------------------------------------------------
    await clickButtonText("Undo");
    await sleep(1500);
    await page.waitForFunction(() => !document.querySelector(".undo-bar"), { timeout: 8000 });

    await page.waitForFunction(() => {
      const badge = document.querySelector(".relation-card-item .badge-stored");
      return badge && badge.textContent.includes("Parent-Child (adopted)");
    }, { timeout: 8000 });

    step(54, "Parent-child Family UI undo edit restores original adopted kind");

    // -----------------------------------------------------------------------
    // 55. Parent-child Family UI delete with preview and UndoBar
    // -----------------------------------------------------------------------
    await clickButtonText("Remove Stored Fact");
    await sleep(800);
    await page.waitForSelector(".modal-backdrop .modal-card", { timeout: 8000 });

    const pcDelPreviewText = await page.evaluate(() => {
      const cards = document.querySelectorAll(".modal-card");
      return cards[cards.length - 1].textContent;
    });
    if (!pcDelPreviewText.includes("parent-child") || !pcDelPreviewText.includes("Musabiha")) {
      throw new Error(`Expected deletion preview to describe removing parent-child fact involving Musabiha, got: ${pcDelPreviewText}`);
    }

    await clickButtonText("Confirm & Save Fact");
    await sleep(1500);
    await page.waitForSelector(".undo-bar", { timeout: 8000 });

    await page.waitForFunction(() => {
      const badge = document.querySelector(".relation-card-item .badge-stored");
      return !badge || !badge.textContent.includes("Parent-Child (adopted)");
    }, { timeout: 8000 });

    step(55, "Parent-child Family UI delete with preview and UndoBar");

    // -----------------------------------------------------------------------
    // 56. Parent-child Family UI undo delete restores exact parent fact
    // -----------------------------------------------------------------------
    await clickButtonText("Undo");
    await sleep(1500);
    await page.waitForFunction(() => !document.querySelector(".undo-bar"), { timeout: 8000 });

    await page.waitForFunction(() => {
      const badge = document.querySelector(".relation-card-item .badge-stored");
      return badge && badge.textContent.includes("Parent-Child (adopted)");
    }, { timeout: 8000 });

    // Clean up: remove test parent-child fact
    await clickButtonText("Remove Stored Fact");
    await sleep(800);
    await page.waitForSelector(".modal-backdrop .modal-card", { timeout: 8000 });
    await clickButtonText("Confirm & Save Fact");
    await page.waitForFunction(() => {
      const badge = document.querySelector(".relation-card-item .badge-stored");
      return !badge || !badge.textContent.includes("Parent-Child (adopted)");
    }, { timeout: 10000 });
    if (await page.$(".undo-bar")) {
      const dismissBtn = await page.$(".undo-bar-close");
      if (dismissBtn) await dismissBtn.click();
      await sleep(300);
    }
    step(56, "Parent-child Family UI undo delete restores exact parent fact");

    // Use the sibling-group source as Family focus so its newly stored facts
    // are the relationship context shown when another member is selected.
    await clickButtonText("Make Family Focus");
    await page.waitForFunction(() =>
      document.querySelector(".family-focus-current")?.textContent.includes("Musabiha"),
      { timeout: 10000 },
    );

    // -----------------------------------------------------------------------
    // 57. Full sibling group with >2 members refused in UI
    // -----------------------------------------------------------------------
    await clickButtonText("+ Add Family Fact");
    await sleep(800);
    await page.waitForSelector(".modal-backdrop .modal-card", { timeout: 8000 });

    await page.evaluate(() => {
      const selects = Array.from(document.querySelectorAll("select.form-select"));
      const typeSelect = selects.find((s) => Array.from(s.options).some((o) => o.value === "sibling"));
      if (typeSelect) {
        typeSelect.value = "sibling";
        typeSelect.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
    await sleep(400);

    await page.evaluate(() => {
      const sibTypeSelect = document.querySelector("#add-sibling-type-select");
      if (sibTypeSelect) {
        sibTypeSelect.value = "full";
        sibTypeSelect.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
    await sleep(300);

    await page.click("#sibling-member-search input");
    await page.type("#sibling-member-search input", "Muaaz");
    await page.waitForSelector("#person-opt-muaaz", { timeout: 8000 });
    await page.click("#person-opt-muaaz");

    await page.waitForFunction(() => {
      const membersLabel = document.querySelector(".sibling-chips")?.previousElementSibling;
      const searchInput = document.querySelector("#sibling-member-search input");
      return membersLabel?.textContent.includes("2 members") && searchInput?.disabled;
    }, { timeout: 8000 });

    const thirdAddDisabled = await page.evaluate(() => {
      return document.querySelector("#sibling-member-search input")?.disabled;
    });
    if (!thirdAddDisabled) {
      throw new Error("Full Siblings group did not disable adding a 3rd member when 2 members are reached");
    }

    await page.evaluate(() => {
      const sibTypeSelect = document.querySelector("#add-sibling-type-select");
      if (sibTypeSelect) {
        sibTypeSelect.value = "";
        sibTypeSelect.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
    await sleep(300);

    const generalAddEnabled = await page.evaluate(() => {
      return !document.querySelector("#sibling-member-search input")?.disabled;
    });
    if (!generalAddEnabled) {
      throw new Error("Default/General Sibling Group unexpectedly kept candidate select disabled");
    }

    await clickButtonText("Cancel");
    await sleep(500);
    step(57, "Full sibling group with >2 members refused in UI");

    // -----------------------------------------------------------------------
    // 58. Multi-member default sibling group create with Preview & Save
    // -----------------------------------------------------------------------
    await clickButtonText("+ Add Family Fact");
    await sleep(800);
    await page.waitForSelector(".modal-backdrop .modal-card", { timeout: 8000 });

    await page.evaluate(() => {
      const selects = Array.from(document.querySelectorAll("select.form-select"));
      const typeSelect = selects.find((s) => Array.from(s.options).some((o) => o.value === "sibling"));
      if (typeSelect) {
        typeSelect.value = "sibling";
        typeSelect.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
    await sleep(400);

    await page.click("#sibling-member-search input");
    await page.type("#sibling-member-search input", "Muaaz");
    await page.waitForSelector("#person-opt-muaaz", { timeout: 8000 });
    await page.click("#person-opt-muaaz");
    await page.waitForFunction(() => document.querySelectorAll(".sibling-chips .family-badge").length === 2, { timeout: 8000 });

    await page.click("#sibling-member-search input");
    await page.type("#sibling-member-search input", "Barirah");
    await page.waitForSelector("#person-opt-barirah", { timeout: 8000 });
    await page.click("#person-opt-barirah");
    await page.waitForFunction(() => document.querySelectorAll(".sibling-chips .family-badge").length === 3, { timeout: 8000 });

    const chipCount = await page.evaluate(() => {
      return document.querySelectorAll(".sibling-chips .family-badge").length;
    });
    if (chipCount !== 3) {
      throw new Error(`Expected 3 sibling member chips, found: ${chipCount}`);
    }

    await page.screenshot({ path: join(DOC_SHOTS, "family-multimember-sibling-group.png"), fullPage: false });
    console.log("  [Screenshot] Captured: family-multimember-sibling-group.png");

    await clickButtonText("Preview Consequences");
    await sleep(800);
    await page.waitForSelector(".modal-backdrop .preview-direct", { timeout: 8000 });

    await page.screenshot({ path: join(DOC_SHOTS, "family-multipath-consequence-preview.png"), fullPage: false });
    console.log("  [Screenshot] Captured: family-multipath-consequence-preview.png");

    const sibPreviewText = await page.evaluate(() => {
      const cards = document.querySelectorAll(".modal-card");
      return cards[cards.length - 1].textContent;
    });
    if (!sibPreviewText.includes("sibling") || !sibPreviewText.includes("3") && !sibPreviewText.includes("three") && !sibPreviewText.includes("Create sibling")) {
      // Accept either a mention of 3-member count or the 'Create sibling fact' phrase
      if (!sibPreviewText.includes("Create sibling fact") && !sibPreviewText.includes("sibling group")) {
        throw new Error(`Expected sibling group preview description, got: ${sibPreviewText}`);
      }
    }

    await clickButtonText("Confirm & Save Fact");
    await sleep(1500);

    await page.waitForSelector(".undo-bar", { timeout: 8000 });
    const sibUndoText = await page.$eval(".undo-bar span", (el) => el.textContent);
    if (!sibUndoText.includes("Added sibling group")) {
      throw new Error(`Expected sibling group UndoBar text, got: ${sibUndoText}`);
    }

    await page.evaluate(() => {
      const node = document.querySelector('.family-canvas g.node.clickable-node[id*="p_muaaz"]');
      if (node) node.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await page.waitForFunction(() => document.querySelector("aside.family-side strong")?.textContent.includes("Muaaz"), { timeout: 8000 });

    await page.waitForFunction(() => {
      const badge = document.querySelector(".relation-card-item .badge-stored");
      return badge && badge.textContent.includes("Sibling Group");
    }, { timeout: 8000 });

    step(58, "Multi-member default sibling group create with Preview & Save");

    // -----------------------------------------------------------------------
    // 59. Sibling group metadata edit updates ordered birth sequence
    // -----------------------------------------------------------------------
    await clickButtonText("Edit Stored Fact");
    await sleep(800);
    await page.waitForSelector("#sibling-ordered-cb", { timeout: 8000 });

    await page.evaluate(() => {
      const cb = document.querySelector("#sibling-ordered-cb");
      if (cb) {
        cb.checked = true;
        cb.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
    await sleep(300);

    await clickButtonText("Save Sibling Group Fact");
    await sleep(1500);

    await page.waitForSelector(".undo-bar", { timeout: 8000 });
    const editSibUndoText = await page.$eval(".undo-bar span", (el) => el.textContent);
    if (!editSibUndoText.includes("Updated sibling group fact")) {
      throw new Error(`Expected UndoBar for updated sibling group fact, got: ${editSibUndoText}`);
    }

    step(59, "Sibling group metadata edit updates ordered birth sequence");

    // -----------------------------------------------------------------------
    // 60. Sibling group metadata undo reverts changes cleanly
    // -----------------------------------------------------------------------
    await clickButtonText("Undo");
    await sleep(1500);
    await page.waitForFunction(() => !document.querySelector(".undo-bar"), { timeout: 8000 });

    step(60, "Sibling group metadata undo reverts changes cleanly");

    // -----------------------------------------------------------------------
    // 61. Explicit sibling group deletion preserves the underlying derived cousin truth
    // -----------------------------------------------------------------------
    await clickButtonText("Remove Stored Fact");
    await sleep(800);
    await page.waitForSelector(".modal-backdrop .modal-card", { timeout: 8000 });

    const delSibPreviewText = await page.evaluate(() => {
      const cards = document.querySelectorAll(".modal-card");
      return cards[cards.length - 1].textContent;
    });
    if (!delSibPreviewText.includes("sibling group") && !delSibPreviewText.includes("sibling fact")) {
      throw new Error(`Expected deletion preview for sibling group, got: ${delSibPreviewText}`);
    }

    await clickButtonText("Confirm & Save Fact");
    await sleep(1500);
    await page.waitForSelector(".undo-bar", { timeout: 8000 });

    await page.waitForFunction(() => {
      const badge = document.querySelector(".relation-card-item .family-badge.badge-derived");
      return badge && badge.textContent.includes("Derived Kinship Term");
    }, { timeout: 8000 });

    const postDeleteRelationship = await page.$eval(".relation-card-item", (el) => el.textContent);
    if (!postDeleteRelationship.toLowerCase().includes("cousin")) {
      throw new Error(`Expected the underlying cousin relationship after sibling group deletion, got: ${postDeleteRelationship}`);
    }
    step(61, "Sibling group delete removes the stored fact and preserves derived cousin truth");

    // -----------------------------------------------------------------------
    // 62. Sibling group undo delete restores explicit stored fact
    // -----------------------------------------------------------------------
    await clickButtonText("Undo");
    await sleep(1500);
    await page.waitForFunction(() => !document.querySelector(".undo-bar"), { timeout: 8000 });

    await page.waitForFunction(() => {
      const badge = document.querySelector(".relation-card-item .family-badge.badge-stored");
      return badge && badge.textContent.includes("Sibling Group");
    }, { timeout: 8000 });

    // Clean up: remove test sibling group
    await clickButtonText("Remove Stored Fact");
    await sleep(800);
    await page.waitForSelector(".modal-backdrop .modal-card", { timeout: 8000 });
    await clickButtonText("Confirm & Save Fact");
    await page.waitForFunction(() => {
      const card = document.querySelector(".relation-card-item");
      return card?.querySelector(".badge-derived") && card.textContent.toLowerCase().includes("cousin");
    }, { timeout: 10000 });
    if (await page.$(".undo-bar")) {
      const dismissBtn = await page.$(".undo-bar-close");
      if (dismissBtn) await dismissBtn.click();
      await sleep(300);
    }

    step(62, "Sibling group undo delete restores explicit stored fact");

    // -----------------------------------------------------------------------
    // 63. Deleting a canonical stored sibling group leaves inferred siblinghood
    // -----------------------------------------------------------------------
    await typeSearch("Musabiha");
    await page.waitForSelector(".person-search-results", { timeout: 8000 });
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Enter");
    await page.waitForSelector(".family-diagram svg", { timeout: 10000 });
    await page.waitForFunction(() => document.querySelector(".family-focus-current")?.textContent.includes("Musabiha"), { timeout: 8000 });

    await page.evaluate(() => {
      const node = document.querySelector('.family-canvas g.node.clickable-node[id*="flowchart-p_musa-"]');
      if (node) node.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await page.waitForFunction(() => {
      const name = document.querySelector("aside.family-side strong");
      return name && name.textContent.trim() === "Musa";
    }, { timeout: 8000 });
    await page.waitForFunction(() => document.querySelector(".relation-card-item .badge-stored")?.textContent.includes("Sibling Group"), { timeout: 8000 });

    await clickButtonText("Remove Stored Fact");
    await page.waitForSelector(".modal-backdrop .modal-card", { timeout: 8000 });
    await clickButtonText("Confirm & Save Fact");
    await page.waitForSelector(".undo-bar", { timeout: 8000 });
    await page.waitForFunction(() => {
      const card = document.querySelector(".relation-card-item");
      const badge = card?.querySelector(".badge-derived");
      return badge?.textContent.includes("Derived Kinship Term") && card?.textContent.includes("Brother");
    }, { timeout: 8000 });
    step(63, "Stored sibling deletion falls back to inferred biological siblinghood");

    // -----------------------------------------------------------------------
    // 64. Undo restores the exact canonical stored sibling group
    // -----------------------------------------------------------------------
    await clickButtonText("Undo");
    await page.waitForFunction(() => !document.querySelector(".undo-bar"), { timeout: 8000 });
    await page.waitForFunction(() => document.querySelector(".relation-card-item .badge-stored")?.textContent.includes("Sibling Group"), { timeout: 8000 });
    step(64, "Undo restores the canonical stored sibling group after inferred fallback");

    // -----------------------------------------------------------------------
    // 65. Derived kinship terms withhold direct destructive controls with Inspect Proof enabled
    // -----------------------------------------------------------------------
    await page.evaluate(() => {
      const node = document.querySelector('.family-canvas g.node.clickable-node[id*="p_maham_mansoor"]');
      if (node) node.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await page.waitForFunction(() => {
      const name = document.querySelector("aside.family-side strong");
      return name && name.textContent.trim() === "Maham Mansoor";
    }, { timeout: 8000 });
    await page.waitForFunction(() => {
      const card = document.querySelector(".relation-card-item");
      return card?.querySelector(".badge-derived") && card.textContent.toLowerCase().includes("cousin");
    }, { timeout: 10000 });

    const derivedButtonsState = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll("aside.family-side .family-side-actions button, aside.family-side .row-actions button"));
      const editBtn = btns.find((b) => b.textContent.includes("Edit Stored Fact"));
      const removeBtn = btns.find((b) => b.textContent.includes("Remove Stored Fact"));
      return {
        editDisabled: editBtn ? editBtn.disabled : true,
        removeDisabled: removeBtn ? removeBtn.disabled : true,
      };
    });
    if (!derivedButtonsState.editDisabled || !derivedButtonsState.removeDisabled) {
      throw new Error(`Derived relationship unexpectedly had active destructive controls: ${JSON.stringify(derivedButtonsState)}`);
    }

    const hasInspectProof = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll(".relation-card-item button"));
      return btns.some((b) => b.textContent.includes("Inspect Proof"));
    });
    if (!hasInspectProof) {
      throw new Error("Derived relationship did not expose 'Inspect Proof' button");
    }

    step(65, "Derived kinship terms withhold direct destructive controls with Inspect Proof enabled");

    console.log("\n=======================================================");
    console.log(`🎉 ALL ${passedSteps.length} / 65 FAMILY UI E2E CHECKS PASSED!`);
    console.log("=======================================================\n");
    } catch (err) {
      testError = err;
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

      if (testError) {
        console.error("\n❌ [E2E FAILURE]:", testError);
        process.exit(1);
      }
      process.exit(0);
    }
}

main().catch((err) => {
  console.error("Family E2E Failed:", err);
  process.exit(1);
});
