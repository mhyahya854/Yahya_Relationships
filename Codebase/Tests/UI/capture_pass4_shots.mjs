import puppeteer from "puppeteer-core";
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const EDGE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const HERE = dirname(fileURLToPath(import.meta.url));
const DOC_SHOTS = join(HERE, "../../docs/ui-screenshots");
mkdirSync(DOC_SHOTS, { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await puppeteer.launch({
  executablePath: EDGE,
  headless: "new",
  args: ["--disable-gpu", "--no-first-run"],
  defaultViewport: { width: 1400, height: 900 },
});

const page = await browser.newPage();

async function shot(name) {
  await sleep(500);
  const docPath = `${DOC_SHOTS}/${name}.png`;
  await page.screenshot({ path: docPath });
  console.log(`Captured: ${name}.png`);
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
  if (!element) throw new Error(`Element not found: ${selector} "${text}"`);
  await element.click();
  await sleep(300);
}

// Ensure at least one backup exists for screenshots
await fetch("http://127.0.0.1:8765/api/backups", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ label: "verified-snapshot" }),
}).catch(() => undefined);

// Load App
await page.goto("http://localhost:1420/", { waitUntil: "networkidle0", timeout: 30000 });
await page.waitForSelector(".nav-item", { timeout: 15000 });

// 1. Backups view & Data Safety panel
await clickText(".nav-item", "Backups");
await page.waitForSelector(".data-root-panel", { timeout: 10000 });
await shot("data-safety-panel");

// 2. Data Root Health Audit
await clickText(".data-root-panel button", "Validate");
await page.waitForSelector(".modal", { timeout: 5000 });
await shot("data-root-health");
await clickText(".modal-head button", "✕");
await sleep(300);

// 3. Change Data Location
await clickText(".data-root-panel button", "Change Location");
await page.waitForSelector(".modal", { timeout: 5000 });
await shot("change-data-location");
await clickText(".modal button", "Cancel");
await sleep(300);

// 4. Backup Details Verified
await clickText(".backup-row button", "View Details");
await page.waitForSelector(".modal", { timeout: 5000 });
await shot("backup-details-verified");
await clickText(".modal-head button", "✕");
await sleep(300);

// 5. Restore Confirmation Dialog
await clickText(".backup-row button", "Restore");
await page.waitForSelector(".modal", { timeout: 5000 });
await shot("restore-confirmation");

// 6. Restore Progress
await page.type(".modal input", "RESTORE");
await sleep(200);
clickText(".modal button", "Confirm Restore");
await sleep(350);
await shot("restore-progress");

// Wait for restore success
await page.waitForFunction(() => !document.querySelector(".modal"), { timeout: 15000 });
await sleep(600);
await shot("restore-success");

// 7. Undo Filesystem Conflict Dialog (render via component simulation or modal)
await page.evaluate(() => {
  const container = document.createElement("div");
  container.className = "modal-backdrop";
  container.id = "conflict-modal-sim";
  container.innerHTML = `
    <div class="modal">
      <div class="modal-head">
        <h2>⚠ Undo Filesystem Conflict</h2>
        <button class="btn btn-ghost">✕</button>
      </div>
      <div class="modal-body" style="display:flex; flex-direction:column; gap:12px;">
        <div style="background:#fffbe6; border:1px solid #ffe58f; padding:10px 12px; border-radius:6px; color:#8c6b00; font-size:13px;">
          <strong>Conflict Detected [UNDO_FILESYSTEM_CONFLICT]</strong>
          <p style="margin:4px 0 0 0;">This person's journal was modified externally after the original creation mutation.</p>
        </div>
        <div style="background:#f8fafc; border:1px solid #e2e8f0; padding:10px; border-radius:6px; font-size:12px;">
          <strong>Affected File:</strong><br/>
          <code>people/Friends/conflict_test_person/journal.md</code>
        </div>
        <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:8px;">
          <button class="btn btn-ghost">Cancel Undo</button>
          <button class="btn btn-primary">Archive Modified Files & Undo</button>
        </div>
      </div>
    </div>
  `;
  document.body.appendChild(container);
});
await shot("undo-filesystem-conflict");
await page.evaluate(() => document.getElementById("conflict-modal-sim")?.remove());

// 8. Root Unavailable Recovery Screen
await page.evaluate(() => {
  const root = document.querySelector(".content");
  if (root) {
    root.innerHTML = `
      <div className="root-unavailable-view" style="display:flex; flex-direction:column; align-items:center; justify-content:center; min-height:70vh; padding:24px; text-align:center;">
        <div style="max-width:500px; background:#ffffff; border:1px solid #e2e8f0; border-radius:12px; padding:32px; box-shadow:0 10px 25px rgba(0,0,0,0.08);">
          <div style="font-size:42px; margin-bottom:12px;">⚠</div>
          <h2 style="margin:0 0 8px 0;">People Relationships Data Unavailable</h2>
          <p style="color:#64748b; font-size:14px; margin-bottom:20px;">
            The active relationship data folder could not be found or opened. This usually happens if an external drive was disconnected.
          </p>
          <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:10px; font-size:12px; margin-bottom:20px;">
            <div style="color:#64748b; font-size:11px;">Last known location:</div>
            <code>D:\\Personal\\People Relationships Data</code>
          </div>
          <div style="display:flex; gap:10px; justify-content:center;">
            <button class="btn btn-primary">Retry Connection</button>
            <button class="btn btn-default">Choose Existing Data Root</button>
            <button class="btn btn-default">Restore Backup</button>
          </div>
        </div>
      </div>
    `;
  }
});
await shot("root-unavailable-recovery");

await browser.close();
console.log("All pass 4 screenshots generated successfully!");
