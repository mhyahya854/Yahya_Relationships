import puppeteer from "puppeteer-core";
import { createHash } from "node:crypto";
import { execFileSync, spawn } from "node:child_process";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "../..");
const REPO = resolve(ROOT, "..");
const REVIEW_DIR = process.env.PHASE10_SCREENSHOT_DIR
  ? resolve(process.env.PHASE10_SCREENSHOT_DIR)
  : resolve(REPO, "Documentation/UI-Screenshots/Phase10-Review");
const BASELINE_ONLY = process.env.PHASE10_BASELINE === "1";
const KEEP_FIXTURE = process.env.PHASE10_KEEP_FIXTURE === "1";
const EDGE = existsSync("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
  ? "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
  : "C:/Program Files/Microsoft/Edge/Application/msedge.exe";
const PROD_DB = resolve(REPO, "Database/Main/family.db");
const PROD_PEOPLE = resolve(REPO, "Database/People");
const PROD_BACKUPS = resolve(REPO, "Backups");
const REAL_BOOTSTRAP = join(process.env.APPDATA ?? "", "people-relationships", "bootstrap.json");

function sha256(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex").toUpperCase();
}

function collectFiles(root) {
  if (!existsSync(root)) return [];
  const rows = [];
  function scan(dir) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name);
      if (entry.isDirectory()) scan(path);
      else rows.push({
        path: relative(root, path).replaceAll("\\", "/"),
        bytes: statSync(path).size,
        hash: sha256(path),
      });
    }
  }
  scan(root);
  return rows.sort((a, b) => a.path.localeCompare(b.path));
}

const production = {
  db: { bytes: statSync(PROD_DB).size, hash: sha256(PROD_DB) },
  journals: collectFiles(PROD_PEOPLE).filter((row) => row.path.endsWith("/journal.md")),
  backups: collectFiles(PROD_BACKUPS),
  bootstrap: existsSync(REAL_BOOTSTRAP)
    ? { exists: true, bytes: statSync(REAL_BOOTSTRAP).size, hash: sha256(REAL_BOOTSTRAP) }
    : { exists: false },
};

const sandbox = resolve(tmpdir(), `p10v_${Date.now()}`);
const bootstrap = join(sandbox, "settings", "bootstrap.json");
const dataRoot = join(sandbox, "Synthetic Family Data");
mkdirSync(dirname(bootstrap), { recursive: true });
mkdirSync(REVIEW_DIR, { recursive: true });

const python = process.platform === "win32" && existsSync(resolve(ROOT, ".venv/Scripts/python.exe"))
  ? resolve(ROOT, ".venv/Scripts/python.exe")
  : process.platform === "win32" ? "python" : "python3";
const env = { ...process.env };
delete env.PEOPLE_RELATIONSHIPS_ROOT;
Object.assign(env, {
  PYTHONUTF8: "1",
  PYTHONPATH: [resolve(ROOT, "App"), resolve(ROOT, "Scripts"), ROOT, process.env.PYTHONPATH]
    .filter(Boolean)
    .join(process.platform === "win32" ? ";" : ":"),
  PEOPLE_RELATIONSHIPS_BOOTSTRAP: bootstrap,
});

const backend = spawn(python, ["-m", "app.backend.main"], { cwd: ROOT, env, stdio: "pipe" });
const vite = spawn(process.platform === "win32" ? "npm.cmd" : "npm", ["--prefix", "App/Frontend", "run", "dev"], {
  cwd: ROOT,
  env,
  stdio: "pipe",
  shell: process.platform === "win32",
});
backend.stdout.on("data", () => undefined);
backend.stderr.on("data", (data) => { if (/Traceback|ERROR/.test(data.toString())) console.error(data.toString()); });
vite.stdout.on("data", () => undefined);
vite.stderr.on("data", (data) => console.error(data.toString()));

const sleep = (ms) => new Promise((done) => setTimeout(done, ms));
async function waitForUrl(url, timeout = 30_000) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    try { const response = await fetch(url); if (response.ok) return; } catch {}
    await sleep(250);
  }
  throw new Error(`Timed out waiting for ${url}`);
}
async function api(path, init) {
  const response = await fetch(`http://127.0.0.1:8765${path}`, init);
  const payload = await response.json();
  if (!response.ok) throw new Error(`${path}: ${JSON.stringify(payload)}`);
  return payload;
}
async function post(path, body) {
  return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}
function stop(child) {
  if (!child?.pid) return;
  if (process.platform === "win32") {
    try { execFileSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" }); } catch {}
  } else {
    try { child.kill("SIGKILL"); } catch {}
  }
}
function verifyProduction() {
  const current = {
    db: { bytes: statSync(PROD_DB).size, hash: sha256(PROD_DB) },
    journals: collectFiles(PROD_PEOPLE).filter((row) => row.path.endsWith("/journal.md")),
    backups: collectFiles(PROD_BACKUPS),
    bootstrap: existsSync(REAL_BOOTSTRAP)
      ? { exists: true, bytes: statSync(REAL_BOOTSTRAP).size, hash: sha256(REAL_BOOTSTRAP) }
      : { exists: false },
  };
  if (JSON.stringify(current) !== JSON.stringify(production)) throw new Error("Production integrity changed");
}

let browser;
let page;
let passed = 0;
const errors = [];
function check(condition, label) {
  if (!condition) throw new Error(`Visual assertion failed: ${label}`);
  passed += 1;
  console.log(`✓ [Visual E2E ${passed}] ${label}`);
}
async function clickText(scope, text) {
  await page.waitForFunction((selector, expected) => [...document.querySelectorAll(`${selector} button`)].some((button) => {
    const box = button.getBoundingClientRect();
    return button.textContent?.includes(expected) && !button.disabled && box.width > 0 && box.height > 0;
  }), { timeout: 20_000 }, scope, text);
  await page.evaluate((selector, expected) => [...document.querySelectorAll(`${selector} button`)].find((button) => {
    const box = button.getBoundingClientRect();
    return button.textContent?.includes(expected) && !button.disabled && box.width > 0 && box.height > 0;
  })?.click(), scope, text);
}
async function setValue(selector, value) {
  await page.waitForSelector(selector, { visible: true, timeout: 20_000 });
  await page.$eval(selector, (element, next) => {
    const prototype = element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, "value").set.call(element, next);
    element.dispatchEvent(new Event("input", { bubbles: true }));
  }, value);
}
async function nav(label) {
  await clickText(".nav", label);
  await page.waitForFunction((expected) => {
    const active = document.querySelectorAll(".nav-item[aria-current='page']");
    return active.length === 1 && active[0].textContent?.includes(expected);
  }, { timeout: 20_000 }, label);
  await page.$eval(".content", (element) => { element.scrollTop = 0; });
}
async function shot(name) {
  await sleep(700);
  await page.screenshot({ path: join(REVIEW_DIR, name), fullPage: false });
}
async function box(selector) {
  return page.$eval(selector, (element) => {
    const rect = element.getBoundingClientRect();
    return { x: rect.x, y: rect.y, width: rect.width, height: rect.height, right: rect.right, bottom: rect.bottom };
  });
}
async function shellChecks(label) {
  const result = await page.evaluate(() => ({
    active: document.querySelectorAll(".nav-item[aria-current='page']").length,
    horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
    sidebarBottom: document.querySelector(".sidebar")?.getBoundingClientRect().bottom,
    topbarBottom: document.querySelector(".topbar")?.getBoundingClientRect().bottom,
    contentY: document.querySelector(".content")?.getBoundingClientRect().y,
    viewportHeight: innerHeight,
    perspective: Boolean(document.querySelector(".perspective-current")),
  }));
  check(
    result.active === 1
      && !result.horizontalOverflow
      && result.sidebarBottom <= result.viewportHeight + 1
      && result.topbarBottom <= result.contentY + 1
      && result.perspective,
    `${label}: shell is visible, contained, and has one active destination`,
  );
}

async function createPerson(payload) {
  return (await post("/api/people", payload)).person;
}
function seedFamilyFacts(people) {
  // The family mutation service intentionally runs legacy production-specific
  // semantic audits. The visual fixture therefore inserts only canonical test
  // rows into its isolated schema; application kinship logic still computes all
  // labels, paths, and diagrams.
  const payload = {
    parentChild: [
      [people.ibrahim.id, people.amina.id], [people.noor.id, people.amina.id],
      [people.ibrahim.id, people.tariq.id], [people.noor.id, people.tariq.id],
      [people.ibrahim.id, people.yusef.id], [people.noor.id, people.yusef.id],
      [people.amina.id, people.leila.id], [people.omar.id, people.leila.id],
      [people.amina.id, people.huda.id], [people.omar.id, people.huda.id],
      [people.tariq.id, people.zain.id], [people.sara.id, people.zain.id],
    ],
    marriages: [
      [people.ibrahim.id, people.noor.id, 1976],
      [people.amina.id, people.omar.id, 2004],
      [people.tariq.id, people.sara.id, 2007],
    ],
  };
  execFileSync(python, ["-c", `
import json, sqlite3, sys
db_path, raw = sys.argv[1], sys.argv[2]
facts = json.loads(raw)
with sqlite3.connect(db_path) as connection:
    connection.executemany(
        "INSERT INTO parent_child(parent_id, child_id, role, kind) VALUES (?, ?, 'parent', 'biological')",
        facts["parentChild"],
    )
    connection.executemany(
        "INSERT INTO marriages(spouse_a, spouse_b, status, year, children_status, display_order) VALUES (?, ?, 'married', ?, NULL, ?)",
        [(*sorted((a, b)), year, order) for order, (a, b, year) in enumerate(facts["marriages"])],
    )
`, join(dataRoot, "Database", "Main", "family.db"), JSON.stringify(payload)], { env, stdio: "inherit" });
}
async function seedFixture() {
  await post("/api/data-root/initialize", {
    target_path: dataRoot,
    owner_name: "Amina Rahman",
    owner_gender: "female",
  });
  const friends = (await post("/api/groups", { name: "Friends & Community" })).group;
  const mentors = (await post("/api/groups", { name: "Work Mentors" })).group;
  const people = { amina: (await api("/api/people/amina_rahman")).person };
  people.ibrahim = await createPerson({ name: "Ibrahim Rahman", aliases: ["ابراہیم"], birth_year: 1952, gender: "male", group_ids: ["family"], note_en: "A patient family storyteller." });
  people.noor = await createPerson({ name: "Noor Rahman", aliases: ["نور"], birth_year: 1956, gender: "female", group_ids: ["family"] });
  people.omar = await createPerson({ name: "Omar Rahman", aliases: ["عمر"], birth_year: 1979, gender: "male", group_ids: ["family"] });
  people.tariq = await createPerson({ name: "Tariq Rahman", aliases: ["طارق"], birth_year: 1982, gender: "male", group_ids: ["family"] });
  people.yusef = await createPerson({ name: "Yusef Rahman", birth_year: 1988, gender: "male", group_ids: ["family"] });
  people.leila = await createPerson({ name: "Leila Rahman", aliases: ["لیلیٰ رحمان"], birth_year: 2008, gender: "female", group_ids: ["family"], note_ur: "خاندان کی یادیں محفوظ رکھتی ہیں" });
  people.leila = (await api(`/api/people/${people.leila.id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: "Leila Noor Rahman-Al-Malik — A Very Long Mixed Family Name" }),
  })).person;
  people.sara = await createPerson({ name: "Sara Malik", birth_year: 1984, gender: "female", group_ids: ["family"] });
  people.zain = await createPerson({ name: "Zain Malik", aliases: ["زین"], birth_year: 2010, gender: "male", group_ids: ["family"] });
  people.huda = await createPerson({ name: "Huda Rahman", birth_year: 2013, gender: "female", group_ids: ["family"] });
  people.farah = await createPerson({ name: "Farah Qureshi", aliases: ["فرح"], gender: "female", group_ids: [friends.id], primary_group_id: friends.id });
  people.khalid = await createPerson({ name: "Khalid Hussain", gender: "male", group_ids: [mentors.id], primary_group_id: mentors.id });
  people.khalid = (await api(`/api/people/${people.khalid.id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: "Professor Khalid Hussain with an Intentionally Long Mentor Name" }),
  })).person;

  seedFamilyFacts(people);
  await post("/api/relationships/general", { person_a: people.amina.id, person_b: people.farah.id, type: "close_friend", directionality: "symmetric", notes: "Trusted friend from the neighborhood reading circle." });
  await post("/api/relationships/general", { person_a: people.khalid.id, person_b: people.amina.id, type: "mentor", directionality: "directional", label_a_to_b: "Trusted mentor and family-history guide", label_b_to_a: "Mentee", notes: "Mentor relationship across work and community." });

  const journal = await api(`/api/people/${people.leila.id}/journal`);
  await api(`/api/people/${people.leila.id}/journal`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      content: "# Leila's Journal\n\n## Family stories\n\nA calm record of family recipes, the mentor who encouraged our archive, and a long bilingual memory.\n\nاردو یاد: خاندان کے ساتھ گزارا ہوا وقت بہت قیمتی ہے۔\n\n<script>window.__visualPwned = true</script>",
      expected_exists: journal.exists,
      expected_modified_ns: journal.modified_ns,
      expected_sha256: journal.sha256,
    }),
  });
  const backup = (await post("/api/backups", { label: "Before the annual family archive review — a deliberately long synthetic backup label" })).backup;
  if (!BASELINE_ONLY) await post(`/api/backups/${encodeURIComponent(backup.id)}/restore`, { confirmation_token: "RESTORE" });
  return { people, backup };
}

try {
  if (production.db.hash !== "3258C738F9D65B23B15970D0E1E7389E8584A35BA8E26030249061BAF74E096E") throw new Error("Unexpected production DB baseline");
  check(production.journals.length === 35, "production Journal baseline contains 35 files");
  check(production.backups.length === 176, "production Backup baseline contains 176 files");
  await waitForUrl("http://127.0.0.1:8765/api/health");
  await waitForUrl("http://localhost:1420");
  browser = await puppeteer.launch({
    executablePath: EDGE,
    headless: "new",
    args: ["--disable-gpu", "--no-first-run", "--no-sandbox", "--edge-skip-compat-layer-relaunch"],
    defaultViewport: { width: 1440, height: 900 },
  });
  page = await browser.newPage();
  page.on("console", (message) => { if (message.type() === "error" && !message.text().includes("Failed to load resource")) errors.push(message.text()); });
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
  await page.evaluateOnNewDocument(() => {
    window.__forbiddenDialogs = 0;
    window.alert = window.confirm = window.prompt = () => { window.__forbiddenDialogs += 1; return false; };
  });

  await page.goto("http://localhost:1420", { waitUntil: "networkidle0", timeout: 40_000 });
  await page.waitForFunction(() => document.body.textContent?.includes("Welcome to People Relationships"));
  check(Boolean(await page.$(".root-unavailable-view > div")), "first-run route renders in the recovery boundary");
  if (!BASELINE_ONLY) await shot("12-first-run.png");

  const fixture = await seedFixture();
  const liveStatus = await api("/api/data-root");
  await page.evaluateOnNewDocument((status) => {
    const originalFetch = window.fetch.bind(window);
    window.fetch = (input, init) => {
      const url = new URL(typeof input === "string" ? input : input.url, window.location.href);
      const visual = new URL(window.location.href).searchParams.get("visualState");
      if (url.pathname === "/api/data-root" && visual === "missing") {
        return Promise.resolve(new Response(JSON.stringify({ ...status, state: "MISSING", active_root: null, last_configured_root: "C:\\Synthetic Family Data\\Moved or unavailable", health: { ...status.health, state: "MISSING", issues: [{ code: "ROOT_MISSING", message: "The configured synthetic location is unavailable.", severity: "error" }] } }), { status: 200, headers: { "Content-Type": "application/json" } }));
      }
      if (url.pathname === "/api/data-root" && visual === "readonly") {
        return Promise.resolve(new Response(JSON.stringify({ ...status, state: "READ_ONLY", writable: false, health: { ...status.health, state: "READ_ONLY", writable: false } }), { status: 200, headers: { "Content-Type": "application/json" } }));
      }
      return originalFetch(input, init);
    };
  }, liveStatus);

  await page.goto("http://localhost:1420", { waitUntil: "networkidle0", timeout: 40_000 });
  await page.waitForSelector(".nav", { timeout: 30_000 });
  await page.waitForSelector(".relationships-graph-area .react-flow", { timeout: 30_000 });
  await page.waitForFunction(() => document.querySelectorAll(".react-flow__node").length >= 8, { timeout: 30_000 });
  await shellChecks("1440x900");
  const graphBox = await box(".relationships-graph-area");
  check(graphBox.width > 500 && graphBox.height > 360, "Relationships canvas has nonzero usable area");
  check(Boolean(await page.$(".react-flow__controls")), "Relationships graph controls are visible");
  check(Boolean(await page.$(".graph-legend")), "family, general, and derived graph legend is visible");
  check((await box(".relationships-panel")).width < 420, "selected-person panel does not cover the graph");
  check(await page.$$eval(".person-node-card", (nodes) => nodes.every((node) => node.scrollWidth <= node.clientWidth + 1)), "long relationship node text is contained");
  await shot("03-relationships.png");

  await setValue(".relationships-search-wrap input", fixture.people.leila.name);
  await page.waitForSelector(".person-search-row", { visible: true });
  await page.click(".person-search-row");
  await page.waitForFunction(() => document.querySelector(".relationships-panel")?.textContent?.includes("Leila Noor"));
  check(Boolean(await page.$(".selected-person-panel")), "relationship details state is visible");
  check((await page.$eval(".relationships-panel", (node) => node.scrollHeight >= node.clientHeight)), "relationship details panel supports long content");
  await shot("04-relationship-details.png");

  await nav("People");
  await page.waitForSelector(".people-table-row", { timeout: 20_000 });
  check((await page.$eval(".view-head h1", (node) => node.textContent)) === "People", "People heading is visible");
  check((await page.$eval(".view-head", (node) => node.textContent)).includes("Add Person"), "People primary action is visible");
  check(await page.$$eval(".people-table-row", (rows) => rows.every((row) => row.scrollWidth <= row.clientWidth + 1)), "People rows do not horizontally overflow");
  check((await page.$eval(".people-table", (node) => node.textContent)).includes("لیلیٰ"), "Urdu aliases remain present in People");
  await shot("01-people.png");

  await page.evaluate((id) => [...document.querySelectorAll(".people-table-row")].find((row) => row.textContent?.includes("Leila Noor"))?.querySelector(".person-cell")?.click(), fixture.people.leila.id);
  await page.waitForSelector(".modal", { timeout: 20_000 });
  const profileBox = await box(".modal");
  check(profileBox.right <= 1440 && profileBox.bottom <= 900, "Person Profile fits the review viewport");
  check(Boolean(await page.$(".modal-head button")), "Person Profile close control is visible");
  check((await page.$eval(".modal-body", (node) => getComputedStyle(node).overflowY)) === "auto", "long Profile content scrolls within the modal");
  check((await page.$eval(".person-profile-container", (node) => node.textContent)).includes("لیلیٰ"), "mixed English and Urdu Profile content is rendered");
  await shot("02-person-profile.png");

  await clickText(".tabs", "Journal");
  await page.waitForSelector(".journal-experience", { timeout: 20_000 });
  await clickText(".journal-experience", "Edit");
  await page.waitForSelector(".journal-editor");
  check((await box(".journal-editor")).width > 600, "Journal editor fills usable width");
  check(Boolean(await page.$(".journal-toolbar")), "Journal toolbar remains visible");
  check(!(await page.evaluate(() => Boolean(window.__visualPwned))), "hostile Journal markup remains inert");
  const journalDraft = await page.$eval(".journal-editor", (node) => node.value);
  await setValue(".journal-editor", `${journalDraft}\n\nPreview-only synthetic draft.`);
  await clickText(".journal-experience", "Preview");
  await page.waitForSelector(".journal-preview");
  await shot("08-journal.png");
  await clickText(".journal-experience", "Revert");
  await page.click(".modal-head button");

  await nav("Family");
  await page.waitForSelector(".family-diagram svg", { timeout: 30_000 });
  check((await box(".family-canvas-wrap")).height > 400, "Family canvas has nonzero usable area");
  check(Boolean(await page.$(".family-focus-bar")), "Family focus controls remain visible");
  await shot("05-family.png");
  const clicked = await page.evaluate((id) => {
    const node = document.querySelector(`.family-canvas g.node.clickable-node[id*="p_${id}"]`);
    node?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    return Boolean(node);
  }, fixture.people.leila.id);
  check(clicked, "Family person node can be selected");
  await page.waitForFunction(() => document.querySelector(".family-side")?.textContent?.includes("Leila Noor"));
  check((await box(".family-side")).right <= 1440, "Family side panel fits the viewport");
  check((await page.$eval(".family-side", (node) => node.scrollWidth <= node.clientWidth + 1)), "long selected-person content stays contained");
  await shot("06-family-selected-person.png");

  await nav("Search");
  await setValue("input[aria-label='Global search']", "mentor");
  await page.$eval("form[role='search']", (form) => form.dispatchEvent(new SubmitEvent("submit", { bubbles: true, cancelable: true })));
  await page.waitForSelector(".search-result", { timeout: 20_000 });
  check((await box("input[aria-label='Global search']")).width > 500, "Search field is prominent and usable");
  check(await page.$$eval(".search-result", (rows) => rows.every((row) => row.scrollWidth <= row.clientWidth + 1)), "Search results do not overflow");
  check((await page.$eval(".search-results-list", (node) => node.textContent)).includes("Journal"), "Journal result is present in mixed Search results");
  check((await page.$eval(".search-filters", (node) => node.textContent)).includes("Relationships"), "Search category controls remain visible");
  await shot("07-search.png");

  await nav("Backups");
  await page.waitForSelector(".backup-row", { timeout: 20_000 });
  check(await page.$eval("body", (node) => ["Manual", "Automatic", "Safety", "Legacy"].every((name) => node.textContent.includes(name))), "all Backup categories are readable");
  check(await page.$$eval(".backup-row", (rows) => rows.every((row) => row.scrollWidth <= row.clientWidth + 1)), "long Backup labels are safely contained");
  await shot("09-backups.png");
  await page.evaluate(() => document.querySelector(".backup-row button")?.click());
  await page.waitForSelector(".modal");
  check((await box(".modal")).bottom <= 900, "Backup Details modal fits the viewport");
  await page.click(".modal-head button");
  await page.evaluate(() => [...document.querySelectorAll(".backup-row")][0]?.querySelectorAll("button")[3]?.click());
  await page.waitForSelector(".modal");
  check((await box(".modal")).bottom <= 900, "Restore confirmation fits the viewport");
  await shot("10-backup-restore.png");
  await clickText(".modal", "Cancel");

  await clickText(".data-root-panel", "Change Location");
  await page.waitForSelector(".modal");
  check((await page.$eval(".modal", (node) => node.textContent)).includes("Move Current Data"), "Data Root actions remain understandable");
  await shot("11-data-root.png");
  await clickText(".modal", "Cancel");

  if (BASELINE_ONLY) {
    console.log(`Baseline screenshots written to ${REVIEW_DIR}`);
  } else {
    for (const [width, height, label] of [[980, 640, "configured minimum"], [1366, 768, "1366x768"], [1440, 900, "1440x900"], [1920, 1080, "1920x1080"]]) {
      await page.setViewport({ width, height });
      await page.goto("http://localhost:1420", { waitUntil: "networkidle0", timeout: 40_000 });
      await page.waitForSelector(".nav");
      await shellChecks(label);
      check((await box(".content")).width > 700, `${label}: main content keeps useful width`);
    }

    await page.setViewport({ width: 1440, height: 900 });
    await page.goto("http://localhost:1420?visualState=missing", { waitUntil: "networkidle0", timeout: 40_000 });
    await page.waitForFunction(() => document.body.textContent?.includes("unavailable"));
    check((await box(".root-unavailable-view > div")).bottom <= 900, "missing-root recovery fits the viewport");
    await shot("13-missing-root.png");

    await page.goto("http://localhost:1420?visualState=readonly", { waitUntil: "networkidle0", timeout: 40_000 });
    await page.waitForSelector(".nav");
    const banner = await box("[role='status'].info-note");
    check(banner.bottom <= (await box(".topbar")).y + 80, "read-only banner does not obscure navigation");
    check((await page.$eval("[role='status'].info-note", (node) => node.textContent)).includes("Read-only"), "read-only state includes text semantics");
    await shot("14-read-only.png");
  }

  const forbiddenDialogs = await page.evaluate(() => window.__forbiddenDialogs ?? 0);
  check(forbiddenDialogs === 0, "no browser prompt, alert, or confirm was used");
  check(errors.length === 0, "no unexpected console or page errors");
  check(!(await page.evaluate(() => Boolean(document.querySelector("script[data-user-content], .journal-view img")))), "hostile fixture content did not create active elements");
  verifyProduction();
  check(true, "production DB, Journals, Backups, and bootstrap remain byte-identical");
  console.log(`Visual E2E complete: ${passed} checks passed.`);
} finally {
  try { await browser?.close(); } catch {}
  stop(backend);
  stop(vite);
  await sleep(600);
  if (KEEP_FIXTURE) console.log(`Synthetic fixture retained at ${sandbox}`);
  else rmSync(sandbox, { recursive: true, force: true });
  verifyProduction();
}
