# People Relationships

> A private, single-user, local-first relationship brain.

**People Relationships** answers one question from **any selected person's
perspective**: *who is connected to whom, how are they related, and what does
that relationship look like from this person's side?*

The application is built around the pre-existing **Family Relationships**
SQLite + Python kinship engine (35 people, 44 parent-child facts, 12
marriages in the current data). That engine is preserved and remains the only
place where genealogy is calculated. React only displays; FastAPI + Python
understand relationships; SQLite stores structured facts; Markdown stores
journal prose; Hermes calls tiny deterministic tools.

---

## What changed (migration summary)

- `family.db` remains the single structured store, now at
  `Database/Main/family.db`. A pre-migration snapshot exists under
  `Backups/Safety/Pre-Upgrade/2026-09-04T130821/` with a SHA-256 manifest,
  and the pre-change baseline is archived at
  `Documentation/Archive/pre-people-relationships-2026-09-04/baseline-before-people-relationships.md`.
- Schema version 1 (`PRAGMA user_version`, `metadata.app_schema_version`)
  was applied transactionally. New tables only add capabilities:
  - `groups`, `person_groups` — organisational metadata (never relationship truth)
  - `general_relationships` — friends/colleagues/mentors and other explicit,
    non-family relationships (symmetric or directional, no transitive inference)
  - `metadata` rows for `app_name`, `app_version`, `app_schema_version`
- Existing tables (`people`, `parent_child`, `marriages`, `sibling_groups`,
  `aliases`, `sources`, `fact_sources`, `review_notes`, `metadata`) are
  untouched. Running the legacy builder (`Codebase/Scripts/build_family.py`)
  after migration reproduced byte-identical `family.md`/`family.html` outputs.
- The legacy builder still works: `npm run legacy:check` from `Codebase/`
  (which runs `Codebase/Scripts/build_family.py --check`) runs the
  full semantic-render, derived-kinship and arbitrary-perspective audits.
- Fourth-pass upgrade snapshot (Data Safety & Restore upgrade):
  `Backups/Safety/Pre-Upgrade/pre-safety-upgrade-2026-09-04T210155/` (database + journals + manifest).

## Data Safety & Portability (Pass 4 Upgrades)

- **Canonical Data Root**: Centralized path resolution via `DataRootManager`. Resolves database (`Database/Main/family.db`), `Database/People/`, `Backups/`, `Database/Config/`, and `Database/Exports/` (legacy layouts — `data/family.db`, root `family.db`, `people/`, `backups/`, `config/`, `exports/` — are still recognized as fallbacks).
- **Filesystem-Aware Undo**: Single-step Undo tracks structured DB changes AND filesystem actions (folder creations/moves). Protects externally modified journals via structured `UNDO_FILESYSTEM_CONFLICT` error.
- **Guided Backup Restore**: Full human-facing restore flow with pre-restore SHA-256 and SQLite integrity verification, mandatory automated pre-restore safety backups (`pre-restore-<timestamp>`), staged atomic execution, and automatic rollback on failure.
- **Data Root Health Audit**: Deterministic, non-destructive audit (`audit_data_root()`) checking SQLite integrity and filesystem alignment (detects missing folders, missing journals, orphan folders, and archived-active mismatches). Includes `safe_repair_data_root()` for safe repairs.
- **Data Root Relocation & Switching**: Supports moving the active data root across drives with copy-verify-switch staging, or switching to an existing valid data root.
- **Disconnected Media Recovery**: If active data root is missing or disconnected on launch, shows a recovery screen offering retry, alternate root selection, or backup restore. Empty databases are never created silently.

## Architecture

```text
Tauri Desktop shell (Codebase/Desktop/Tauri)
        |
        v
React + TypeScript + Vite (Codebase/App/Frontend)
        |
        v  http://127.0.0.1:8765
FastAPI local backend (Codebase/App/app/backend)
        |
        +---- Python relationship engine (canonical domain/family/engine.py, reused)
        +---- SQLite Database/Main/family.db (structured facts + app tables)
        +---- Database/People/<group>/<person-id>/journal.md (Markdown prose)
```

Repository layout (the repo root is also the personal-data root):

```text
Family Relationships/
  Codebase/              application source, tests, scripts and packaging
    App/app/backend/     FastAPI + services + Hermes tools
      domain/family/     canonical engine + engine-aligned path extraction
      domain/relationships/ path service + graph neighbour model
    App/Frontend/        React UI
      src/features/relationships/ diagram-first React Flow feature
    Desktop/Tauri/       Tauri 2 desktop shell
    Scripts/             dev / verify helpers + build_family.py CLI wrapper
    Tests/Backend/       pytest suite (93 tests)
    Tests/UI/            headless Edge smoke test
    Resources/Vendor/    bundled third-party assets (mermaid.min.js)
  Database/
    Main/family.db       canonical SQLite store (unchanged schema core)
    People/<Group>/<id>/journal.md
    Config/state.json    UI perspective state
    Sources/             provenance source batches
    Exports/Family/      family.html / family.md (still generated)
  Backups/<Category>/<timestamp>/  full snapshots + manifest.json
  Documentation/         architecture, API, database, testing docs + archive
```

## Relationships is diagram-first (React Flow)

Opening **Relationships** shows a relationship diagram immediately, with a
side panel beside it. The diagram is rendered with **@xyflow/react** and a
deterministic **dagre** hierarchical layout — no physics-based jitter — and
starts with the perspective person plus their parents, siblings, spouses and
general neighbours.

- Click a node to select; double-click (or *View from this person*) to change
  the global perspective. **Return to My Perspective** stays prominent.
- The bottom bar expands/collapses **Parents · Children · Siblings · Spouses
  · General** for the selected person. Nodes shared with other visible
  branches are never removed when collapsing.
- Edges are semantic: strong line = parent/child (biological), dashed amber =
  non-biological parent/child kind, medium violet = marriage, dotted = sibling,
  dashed teal = general relationship. A small legend is always visible.
- The **Family** screen remains the existing Mermaid genealogy renderer;
  Relationships (exploratory, arbitrary perspective) and Family (traditional
  tree) solve different problems on purpose.

### Show why and relationship paths

Every Primary/Additional relationship in the side panel has a **Show why**
button. It asks the backend for the exact objective graph path(s), enters
path-focus mode, highlights the path nodes and edges, dims everything else,
adds missing intermediate (including virtual shared-ancestor) nodes, fits the
path into view, and shows side/degree/removal/common-ancestor facts plus a
template-generated explanation. **Esc** or *Exit path* restores the previous
graph. Multiple valid paths for one label (for example a nephew via the
maternal grandmother vs. the maternal grandfather) can be switched inside
the path panel.

Paths are bounded and validated: `max_depth` default 10 (range 1–30) and
`max_paths` default 10 (range 1–50). Errors are structured
(`NO_RELATIONSHIP_PATH`, `INVALID_MAX_DEPTH`, `INVALID_MAX_PATHS`). Paths are
derived data — never stored, never authoritative. See
[Documentation/Architecture/relationship-paths.md](Documentation/Architecture/relationship-paths.md).

### Keyboard navigation

| Key | Action |
| --- | --- |
| Ctrl/Cmd+K | Focus person search |
| V | View from selected person |
| C | Compare selected person |
| P | Show primary relationship path |
| H | Return to owner perspective |
| Esc | Exit path focus / close overlay |

Shortcuts never fire while typing in inputs, textareas or editors.

## Family engine preservation

The existing engine (canonical at `Codebase/App/app/backend/domain/family/engine.py`,
with `Codebase/Scripts/build_family.py` as a thin CLI wrapper) is **not**
reimplemented. The new backend imports the same functions the legacy export
uses:

- `read_sqlite_model` / model loading
- `validate` (duplicates, self-parent, ancestry cycles, kinds, statuses)
- `_pair_path_records` (every distinct lineage path)
- `_kinship_terms`, `_pair_relationship_entries` (maternal/paternal sides,
  cousin degree/removal, multiple simultaneous paths)
- `_audit_derived` and `_kinship_regression_audit` (build-time regression
  audits)
- `build_mermaid`, `audit_render_mapping` (family diagram generation)

`Codebase/App/app/backend/kinship/` is a thin facade over the builder plus a
display-language layer that attaches stable semantic type keys (for example
`maternal_cousin_degree_1`) and English/Urdu labels without changing kinship
logic. The UI never computes family relationships itself.

## Perspective switching

The whole UI is interpreted from a `perspective_person_id`:

1. Default = the configured owner/focus person from `Database/Main/family.db`
   (`mohammad_yahya_hussain`).
2. The top bar always shows **Viewing relationships from: [Person]** and a
   **Return to My Perspective** action when a different person is selected.
3. Every person card/modal offers **View from this person**.
4. Perspective is UI/session state stored in `Database/Config/state.json`; it
   never rewrites family facts.
5. Double-clicking a card in the Family diagram or the network view also
   switches perspective.

Relationships are directional. `get_relationship(A, B)` differs from
`get_relationship(B, A)` wherever terminology is directional (Uncle vs
Nephew, etc.). Multiple valid paths are first-class: direct relationships
appear under *Primary*, additional cousin paths under *Additional paths*.

## Generic (non-family) relationships

Stored in `general_relationships` with `person_a`, `person_b`, `type`,
`directionality`, `label_a_to_b`, `label_b_to_a` and notes. Symmetric types
(friend, close_friend, colleague, neighbour, acquaintance…) receive one
label; directional relationships (mentor → mentee) keep distinct labels and
the original direction. No friendship is ever inferred transitively.
Relationships are independent of groups — a person can simultaneously be
family, friend and colleague while remaining one canonical record with one
folder.

## Per-person Markdown journals

- Every person has exactly one folder: `Database/People/<primary-group>/<id>/journal.md`
- `journal.md` is the authoritative prose source (UTF-8, any language).
- The app reads the file on open and offers **Reload from disk**, so edits in
  VS Code / Obsidian / Notepad appear without a restart.
- Writes are atomic (temp file + `fsync` + rename). If the file changed on
  disk since it was read, the app refuses to overwrite it (`JOURNAL_CONFLICT`)
  and reloads the external version for manual merge.
- Search reads the journals directly; no competing authoritative copy.

## Hermes tool layer

`GET /api/hermes/tools` exposes a small stable catalog; `POST
/api/hermes/run` executes one tool. Hermes decides intent; the backend
performs the operation — including genealogy. Tools include:

```text
search_people        get_person            list_people
get_relationship     compare_people        list_relationships_from
set_perspective      add_person            update_person
add_family_fact      add_general_relationship  remove_general_relationship
read_journal         append_journal        search_journals
create_backup        list_backups          resolve_person
get_relationship_paths                    get_neighbors
```

Every tool returns `{"ok": true, ...}` or a machine-readable error
`{"ok": false, "error": {"code": ..., "message": ...}}`. Ambiguous names
return `PERSON_AMBIGUOUS` with candidate matches rather than silent guesses.
Hermes-created writes carry provenance `source_type=user_via_hermes`.
No tool exposes SQL, internal paths, or the repository structure.

## Backups

`Create Backup` in the Backups screen (or the `create_backup` Hermes tool)
snapshots the whole state into `Backups/` (categorized under `Manual/`,
`Automatic/` or `Safety/…`; each snapshot folder is named
`backup-<UTC-timestamp>-<label>`):

- `data/family.db` (SQLite copy)
- `people/` (every journal folder, UTF-8)
- `config/`
- `manifest.json` — app/schema version, file list with sizes and SHA-256

Snapshots can be verified against the manifest and restored by copying files
back (the database file is a plain SQLite file; journals are plain Markdown).

## Development

Prerequisites: Python 3.11+, Node 20+, Rust stable + MSVC (for the desktop
shell), and a local copy of `Codebase/Resources/Vendor/mermaid.min.js`
already present.

All development commands run from `Codebase/`:

```powershell
# Unified one-command setup (creates .venv, installs editable backend, installs npm dependencies)
npm run setup

# Or manual setup:
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e App
npm install
npm --prefix App/Frontend install

# Everything (FastAPI + Vite), open http://localhost:1420
npm run dev

# Desktop shell (starts Vite, compiles and opens the Tauri app)
npm run dev:desktop

# Production web build (also used by Tauri)
npm run build

# Tests
npm test              # Python/pytest suite (93 tests)
npm run legacy:check  # legacy builder audits against Database/Main/family.db
```

The backend binds to `127.0.0.1:8765` by default
(`PR_BACKEND_PORT` overrides; Vite proxies `/api` in development). The Tauri
shell starts the backend automatically when launched from a source checkout
(uses `Codebase/.venv/Scripts/python.exe` when present). For a fully standalone
packaged build, bundle the backend with PyInstaller and point
`PR_BACKEND_EXE` at it — the desktop shell treats that environment variable
as the backend command. No cloud service is used anywhere.

## Data-integrity rules carried over

- Stable person IDs; one real person = one record = one folder.
- Parent-child kinds are validated (`biological`, `adopted`, `step`,
  `foster`, `guardian`, `unknown`, `unspecified`); ancestry cycles,
  duplicates and self-marriages are rejected.
- No-children, single-status and sibling-group rules match the legacy
  `validate()` implementation.
- Family writes re-run the legacy derived-kinship and arbitrary-perspective
  audits after every successful mutation.
- Deletions are refused while the person is part of the family graph; strong
  confirmation is required in the UI.

## Tests

`Codebase/Tests/Backend/` (93 tests) cover data integrity, kinship
regressions, perspective reversal, multiple simultaneous paths, compare,
generic relationships and no-transitive-inference, journals (append, UTF-8,
external-edit detection), backups, Hermes JSON tools, relationship paths
(endpoints, bounds, dedupe, reversal, coverage), data root safety resolution,
and the FastAPI endpoints.
Tests always run against a fresh copy of `family.db` in a temporary root;
the real database is never mutated by tests. A headless Edge UI smoke test
(`Codebase/Tests/UI/smoke.mjs`) drives the diagram-first acceptance flow
end-to-end against the running dev stack (see `Codebase/Tests/UI/README.md`).
Verified screenshots live in `Documentation/UI-Screenshots/`.

## Supported Platforms

People Relationships is distributed as a self-contained desktop application with no requirement for end users to install Python, Node.js, or Rust:

| Platform | Architecture | Distribution Package | Status |
|---|---|---|---|
| **Windows** | x64 (`x86_64`) | NSIS Installer (`.exe`) / MSI | Locally built and tested |
| **macOS** | Apple Silicon (`arm64`) | `.app` bundle / DMG | Packaged via native CI runner |
| **macOS** | Intel (`x86_64`) | `.app` bundle / DMG | Packaged via native CI runner |
| **Linux** | x64 (`x86_64`) | AppImage / `.deb` | Packaged via native CI runner |

---

## Installation & Launch

### Windows Installation
1. Download the latest installer: `People-Relationships-<version>-windows-x64-setup.exe` (or from `Codebase/Packaging/release/`).
2. Run the installer. It installs the application to your user profile (`%LOCALAPPDATA%\Programs\People Relationships`) without requiring administrator permissions.
3. Launch **People Relationships** from the Start Menu or desktop shortcut.
4. *SmartScreen note*: Development builds are unsigned. If Windows SmartScreen appears, click **More info** -> **Run anyway**.
5. *Uninstall*: Removing the application via Windows Settings / Control Panel completely removes application binaries but **preserves** your relationship data root and database.

### macOS Installation
1. Download `People-Relationships-<version>-macos-arm64.dmg` (for M1/M2/M3/M4 Macs) or `People-Relationships-<version>-macos-x64.dmg` (for Intel Macs).
2. Open the `.dmg` and drag **People Relationships** to your `/Applications` folder.
3. Launch **People Relationships**.
4. *Gatekeeper note*: As open-source development builds are not notarized by Apple, on first launch right-click the app in Finder and choose **Open**, or visit **System Settings -> Privacy & Security** and click **Open Anyway**.

### Linux Installation
1. Download `People-Relationships-<version>-linux-x64.AppImage` (or the `.deb` package).
2. Make the AppImage executable: `chmod +x People-Relationships-*-linux-x64.AppImage`.
3. Run the AppImage: `./People-Relationships-*-linux-x64.AppImage`.
4. *Runtime libraries*: Standard Tauri Linux dependencies apply (`webkit2gtk-4.1` or `webkit2gtk-4.0`, `gtk3`). On Ubuntu/Debian: `sudo apt install libwebkit2gtk-4.1-0 libgtk-3-0`.

---

## Portable Relationship Data

Your family relationship brain is completely decoupled from application binaries. A Data Root created on one operating system can be transferred directly to another without modification:

```text
Family Relationships/
├── Database/
│   ├── Main/
│   │   └── family.db         # Standard SQLite 3 database (PRAGMA integrity_check clean)
│   ├── People/
│   │   └── <Group>/<PersonID>/journal.md  # Universal UTF-8 Markdown journals
│   ├── Config/
│   │   └── state.json        # UI perspective state
│   └── Exports/
└── Backups/
```

### Moving Data Between OSes
1. **Copy the directory**: Copy your relationship data folder (e.g. via flash drive, local network, or archive) to the destination machine.
2. **Open People Relationships**:
   - If this is a first run, select **[Use Existing Data Folder]** and choose the directory.
   - If the app is already configured, switch the active data root via the UI settings or relocate dialog.
3. **Paths and encoding**: All internal references use relative paths (`/`) and filesystem-safe person IDs. Markdown journals are strictly UTF-8 and tolerate CRLF/LF line endings interchangeably.

### Bootstrap Configuration
The pointer to the active relationship data root is stored in standard OS configuration directories:
- **Windows**: `%APPDATA%\people-relationships\config.json`
- **macOS**: `~/Library/Application Support/people-relationships/config.json`
- **Linux**: `~/.config/people-relationships/config.json` (or `$XDG_CONFIG_HOME/people-relationships/config.json`)

---

## Security & Local Privacy

- **100% Offline & Local-First**: No telemetry, analytics, or cloud connectivity.
- **Strict Loopback Binding**: The backend binds exclusively to `127.0.0.1` on a dynamically allocated port. It is never exposed to the local network.
- **Process Isolation**: Tauri manages the backend lifecycle directly, spawning it on launch and cleanly terminating it on shutdown.
- **Data Safety on Uninstall**: Uninstalling the software deletes only application binaries and temporary caches. Your relationship database, journals, and backups are **never** deleted by uninstallation.

---

## Building Packages

Packaging scripts are fully cross-platform and orchestrate frontend compilation, PyInstaller backend sidecar bundling, Tauri desktop bundling, and release manifest generation:

```bash
# In Codebase/

# Package for current host OS:
npm run package

# Target-specific shortcuts:
npm run package:windows   # Builds NSIS installer & sidecar on Windows host
npm run package:macos     # Configured for macOS host / CI runner
npm run package:linux     # Configured for Linux host / CI runner
```

Automated multi-platform CI workflows are defined in `.github/workflows/build-and-package.yml` for `windows-latest`, `macos-14` (Apple Silicon), `macos-13` (Intel), and `ubuntu-latest`.

---

## Development

Prerequisites: Python 3.11+, Node 20+, Rust stable + MSVC / clang (for the desktop shell).

All development commands run from `Codebase/`:

```powershell
# Unified one-command setup (creates .venv, installs editable backend, installs npm dependencies)
npm run setup

# Or manual setup:
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e App
npm install
npm --prefix App/Frontend install

# Everything (FastAPI + Vite), open http://localhost:1420
npm run dev

# Desktop shell (starts Vite, compiles and opens the Tauri app)
npm run dev:desktop

# Production web build (also used by Tauri)
npm run build

# Tests
npm test              # Python/pytest suite (99 tests)
npm run legacy:check  # legacy builder audits against Database/Main/family.db
```

---

## Architecture & Detailed Documentation

For in-depth architectural and testing documentation, see:
- [Cross-Platform Packaging Architecture](Documentation/Architecture/cross-platform-packaging.md)
- [Platform Compatibility Matrix](Documentation/Testing/platform-compatibility.md)
- [Data Root Architecture & Safety](Documentation/Architecture/data-root.md)
- [Backup and Restore Design](Documentation/Architecture/backup-restore.md)
- [Relationship Paths & Invariants](Documentation/Architecture/relationship-paths.md)
