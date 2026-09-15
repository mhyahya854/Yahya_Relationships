# Mosaic

> Your private people, memories & connections archive.

## Master architecture authority

This README is the repository's authoritative Master Plan. The consolidated
people, media, memories, conversations, and location architecture below is an
approved **documentation authority update only**: it does not authorize an
implementation, data migration, UI redesign, automatic organization, or any
change to application behavior.

The application remains single-user, local-first, human-readable wherever
practical, deterministic for derivable facts, and easy for both people and
coding agents to navigate. Its governing design principle is:

> **Minimal physical architecture, rich logical structure.**

The current checkout contains implementation-era paths and compatibility
details. Those are historical/current-state notes only where identified as
such; they do not override the locked forward architecture in this Master
Plan. In particular, no database, file, or source material is moved by this
documentation update.

**Mosaic** answers one question from **any selected person's
perspective**: *who is connected to whom, how are they related, and what does
that relationship look like from this person's side?*

Mosaic is a private, single-user, local-first system for people,
relationships, memories, conversations, media, events, and places. The
application is built around the pre-existing SQLite + Python kinship engine (35 people, 44 parent-child facts, 12
marriages in the current data). That engine is preserved and remains the only
place where genealogy is calculated. React only displays; FastAPI + Python
understand relationships; SQLite stores structured facts; Markdown stores
journal prose; Hermes calls tiny deterministic tools.

## Phase roadmap and current UI freeze

### Phase 10 — Visual Design

**STATUS: FROZEN FOR LATER REVIEW.** The visual system and current screens are
technically stable enough to serve as the development baseline for subsequent
phases. This freeze does not constitute permanent final visual approval.
Non-blocking visual refinements are deliberately deferred until the dedicated
whole-app UI review after the major remaining feature phases. Later phases must
not casually redesign existing screens; visual changes should be limited to
what their new feature requires.

- Phase 11 — Canonical Data Foundation & Migration
- Phase 12 — Raw Intake, Provenance & Organization
- Phase 13 — Media, Documents & Gallery
- Phase 14 — Events, Memories & Flashbacks
- Phase 15 — Conversations & Social Media Archive
- Phase 16 — Places, Location History & Travel
- Phase 17 — Face Recognition & Identity Review
- Phase 18 — Accessibility & QoL
- Phase 19 — Edge Cases, Data Integrity & Expanded Backups
- Phase 20 — Full Cross-Feature QA
- Phase 21 — Final Whole-App UI Review & Polish — explicitly unfreezes the UI
  for final holistic review.
- Phase 22 — Release Hardening & Packaging
- Phase 23 — V1 Release

The deferred, non-binding review prompts are tracked in
[final-ui-review-backlog.md](Documentation/Planning/final-ui-review-backlog.md).
Expanded Hermes remains deferred unless separately approved; it is not a
required V1 phase.

---

## Historical implementation notes (non-authoritative for new work)

- The current implementation has a historical single-store snapshot. It
  remains untouched by this task and is not a second target database or a
  prescription for future expansion. A pre-migration snapshot exists under
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

- **Canonical Data Root**: Centralized path resolution via `DataRootManager`, with explicit `UNCONFIGURED`, `HEALTHY`, `READ_ONLY`, `MISSING`, `INVALID`, `REPAIRABLE`, and `MAINTENANCE` states. Status and candidate inspection are read-only; an explicit bootstrap override never falls back to source data.
- **Filesystem-Aware Undo**: Single-step Undo tracks structured DB changes AND filesystem actions (folder creations/moves). Protects externally modified journals via structured `UNDO_FILESYSTEM_CONFLICT` error.
- **Guided Backup Restore**: Full human-facing restore flow with strict manifest/path/hash/size/count/schema verification, mandatory verified `Safety/Pre-Restore` snapshots, reversible staged DB/People/Config switching, exact rollback, and post-restore health checks.
- **Data Root Health Audit**: Deterministic, non-destructive audit (`audit_data_root()`) checking SQLite integrity and filesystem alignment (detects missing folders, missing journals, orphan folders, and archived-active mismatches). Includes `safe_repair_data_root()` for safe repairs.
- **Atomic Data Root Onboarding**: Create New stages a schema-2 root with a user-provided owner, validates it, publishes it, and atomically commits the OS-local pointer last. Existing nonempty locations are never reused or overwritten.
- **Data Root Relocation & Switching**: Existing roots are inspected and confirmed before atomic switching. Move creates a verified safety backup and copies only runtime `Database/` and `Backups/` payload with exact inventory verification; source `Codebase/` and `Documentation/` trees are excluded and the old root is retained.
- **First-Run Restore**: A verified backup source is restored into a separately selected empty destination through staging, then activated pointer-last; the backup source remains unchanged.
- **Disconnected / Invalid Location Recovery**: Reachable backend plus missing, malformed, or invalid root opens the appropriate recovery flow, while actual backend failure alone opens service-failure UX. Empty databases are never created silently.

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
        +---- Database/relationships.db (locked future canonical structured truth)
        +---- People/<group>/<person-id>/... (locked Markdown/context hierarchy)
```

Repository layout (the repo root is also the personal-data root):

```text
<Existing Data Root>/    # e.g. an existing Family Relationships/ folder; no rename required
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
    relationships.db     locked future canonical SQLite store
    raw_processing_history.md
    Sources/             provenance source batches
    Exports/Family/      family.html / family.md (still generated)
  People/                locked person records and person-specific context
  Media/                 locked ordinary event-based media hierarchy
  Raw/                   locked open intake; source material remains untouched
  Backups/<Category>/<backup-id>/  full snapshots + manifest.json
  Documentation/         architecture, API, database, testing docs + archive
```

## Consolidated people, media, memories, conversations, and location architecture

### Scope, truth, and implementation boundary — LOCKED

This is one private, single-user personal relationship application. It brings
together relationship/family knowledge, person identities, personal memories,
events, ordinary photos/videos, social-media conversations and their media,
location history/travel, documents, face-reference material, and future Hermes
access. It uses structured metadata and cross-links instead of duplicated
physical copies.

This plan extends rather than replaces the established application: React +
TypeScript + Vite, Tauri 2, a Python/FastAPI loopback backend, SQLite structured
truth, Markdown context, the canonical Python family engine, Mermaid Family
Tree, React Flow + Dagre Connections, perspective-aware relationships, all
valid family paths, and current navigation/design authority all remain intact.

No feature described in this section is being implemented by this document.
Unknown is a valid recorded state; AI suggestions never become confirmed facts
without the user's approval.

### One database and canonical identifiers — LOCKED

There is exactly one forward-architecture SQLite database:

```text
Database/
└── relationships.db
```

It has logically separated tables for people, relationships and their
aliases/statuses, groups and memberships, places, events, memories/indexes,
media assets and links, conversations/messages/message-media links, platform
identities, unresolved people, face references/indexes, raw processing,
provenance, and identifier alias/history. Names are display information;
cross-references use canonical IDs. No separate `me`, `family`, `friends`,
`other`, `core`, `context`, or `index` database is approved.

Known people have permanent readable IDs of the form
`normalized_full_name--INITIALS##`, for example `sara_khan--SK01` or
`mohammad_yahya_hussain--MYH01`. The normalized portion is lowercase with
underscores; initials are uppercase for every full-name part; the two-digit
counter separates identical normalized names. Aliases, nicknames, and later
display-name changes never change the canonical ID. The owner uses an ordinary
person ID; the setting merely points to it.

Unidentified people receive stable temporary IDs such as
`unknown_person--UP0001`, live directly under `People/`, and retain all known
context (source, place seen, event, approximate date, media, and face
reference). Resolving an identity creates the normal known-person ID while
permanently retaining the old temporary identifier in alias/history/provenance;
no existing link may be silently lost.

Future Hermes receives one unified backend/query interface, so it never needs
to know a table or physical file location. A future request such as “everything
about Sara” resolves a structured package of identity, relationships, groups,
media, conversations, events, memories, places, and documents. Hermes itself,
including security/masking behavior, remains **DEFERRED**.

### People, status, groups, and person files — LOCKED

```text
People/
├── Me/
├── Family/
├── Friends/
├── unknown_person--UP0001/
└── unknown_person--UP0002/
```

`Me`, `Family`, and `Friends` use the same template. A person who is both
family and friend has one folder under `Family`; friendship is an additional
relationship, never a duplicate person. Friends remain direct children of
`People/Friends/`: social/friend groups are logical records with readable IDs,
membership history, alternative names, and context, not nested person folders.
Shared group membership never implies friendship.

Known historical people remain known even after contact ends. Relationship and
contact fields can record Friend, Close/Best/Childhood Friend, Former Friend,
Acquaintance, Colleague/Former Colleague, Mentor/Mentee, Neighbour, Enemy, No
Contact, or a custom relationship, together with ending terms and flashback
preference. Bad endings do not erase identity, chats, events, media, groups,
face references, memories, or other historical truth.

```text
sara_khan--SK01/
├── sara_khan--SK01(facts and about).md
├── journal(personal thoughts).md
├── Memories(personal history)/
├── Conversations (Social Media chats)/
├── Documents (Documents about the person)/
├── Face (for the apps face detection)/
└── Profile (Profile Picture)/
```

The facts-and-about file is the predictable first-read identity record. It
preserves canonical ID, names/aliases, known birth date, contact details,
current and historical phone/email/platform identities, how/when/where the
person was met, category/relationships, groups, contact and relationship
history, identity-link evidence/notes, and created/updated/verification dates.
Historical usernames and numbers must be retained to prevent old and new
exports from creating duplicate people. `journal(personal thoughts).md` is
only the freeform human-written area for reflections, stories, and informal
history; it is not a substitute structured identity record.

`Profile (Profile Picture)/` holds current and historical profile images. Each
has a same-basename Markdown sidecar with setting/replacement date/time,
source, location context, and provenance when known. `Face (for the apps face
detection)/` holds confirmed references for that person; recognition can only
suggest an identity, never automatically confirm it. Unknown faces keep stable
unresolved references. Face engine/model selection is **DEFERRED**.

### Raw intake, provenance, and retention — LOCKED

`Raw/` is an open intake area for files, folders, ZIPs, platform exports, phone
backups, photos, videos, documents, location exports, social-media exports, and
unknown material. It is never pre-organized by the user and remains untouched
while unresolved: no silent unpacking, modification, deletion, or move is
allowed.

```text
Raw → scan → classify → hash/dedupe → extract metadata/OCR/transcription/
face/location processing → AI suggestions → proposed destination → user review
→ approval → canonical move → logged result
```

Before an item leaves `Raw/`, record its understood type, hash/duplicate check,
canonical destination, completed required sidecar, provenance, date and people
states, AI-generated fields, and explicit unresolved fields. Exact,
Approximate, and Unknown are valid date/identity states. An unresolved person
with a stable unresolved reference does not alone block processing. AI may
analyze and propose, but only a user-approved action may move a canonical file.

One human-readable processing history is maintained at
`Database/raw_processing_history.md` unless a later established authoritative
location supersedes that path. It keeps original filename/path/hash, type,
duplicate finding, extraction, proposed and final destinations, user decision,
move/deletion date, corrections, and provenance. Identical duplicates may be
detected automatically but are deleted only after explicit authorization and a
preserved history record.

### Ordinary media, events, sidecars, and documents — LOCKED

Ordinary camera/standalone photos and videos are stored once, chronologically,
in the event that actually occurred:

```text
Media/
└── Friends and Family/
    └── 2026/
        └── 2026-09-14 - Sara Birthday Dinner/
            ├── event.md
            ├── location.md
            ├── timeline.md
            ├── Memories/
            ├── IMG_8127.jpg
            ├── IMG_8127.md
            ├── VID_2204.mov
            └── VID_2204.md
```

The event folder is the canonical physical home. Person, gallery, travel,
memory, and flashback views reference assets without copying them into every
person folder. `event.md` records a readable permanent event ID, name,
exact/approximate date and timing, canonical participant/group IDs, type,
context, provenance, related media/memories/conversations, place reference,
and confirmation status. `location.md` records place/address/coordinates and
accuracy, arrival/departure, evidence (GPS, EXIF, imported history, manual, or
AI suggestion), corrections, and confirmation. `timeline.md` can connect
visits, routes, assets, conversations, people, and sub-events/moments by time.

Every photo, video, audio file, and document has a same-basename Markdown
sidecar. The rigid structure separates: (1) structured metadata, (2) AI
analysis, (3) human-confirmed information, and (4) freeform note/context.
Asset metadata includes permanent ID, original/current path, hash, type,
date/accuracy/acquisition, relevant original metadata, location, device,
photographer, people/face evidence, groups, event, provenance, and related
media. AI suggestions retain confidence; confirmed values and corrections are
separate. Useful high-confidence EXIF is preserved without blindly dumping all
fields. Photographer values support canonical person, unresolved person, self,
timer, screenshot, downloaded, or unknown.

Video sidecars also support duration, resolution, language, transcript and
confidence, speaker turns, timestamped visible people, and scene/event/location
context. All technically possible audio—including voice notes and applicable
video audio—is transcribed with timestamps/speakers/language/confidence and
uncertain passages. Fact-sensitive transcription remains unconfirmed until
user approval. Person documents live in their Documents folder, have matching
sidecars, and can record owner, document type/number, dates, issuer/country,
language, OCR text, mentioned people, provenance, filename/hash, corrections,
and notes. OCR should run when technically possible. Hermes document-security
behavior is **DEFERRED**.

### Locations, travel, and places — LOCKED

Location exports first enter `Raw/`. Source names, including Google Timeline,
Google Location History, and Import, belong in provenance—not canonical
folders. The normalized model uses generic places, visits, routes, trips, and
timeline information. Place records are global, never person-specific copies,
and support names/alternatives, coordinates and accuracy, address, type,
first/last known visits, notes, and provenance. A recurring concept such as
Home may map to different physical addresses across date ranges. Places use a
stable internal database identifier when needed; no readable place-ID convention
is approved.

Photo/video time plus GPS and location history may suggest place, event, visit,
or route associations, but they remain `Suggested` until user approval. The
future Travel view will present normalized chronology—years, trips, events,
places, routes, media, people, and memories—by referencing canonical files
without duplication. Exact map/offline stack is **DEFERRED**. Immich and
Dawarich are future reference sources for concepts only; no code, assets,
architecture, or model may be copied without review, including license review.

### Memories and flashbacks — LOCKED

A memory is structured personal meaning or narrative, not simply a media file.
It can refer to people, events, places, conversations, photos, videos, or
documents. It has one primary home: person-specific memories live in that
person's `Memories(personal history)/`; event-specific memories live in that
event's `Memories/`. One event can have many memories; a memory normally has
one primary event and is not copied to every participant. An event is the
objective occurrence; a memory is the user's recollection or meaning connected
to it.

Future Flashbacks may cover On This Day, family/friends/person/group, place,
event anniversary, and trips. `Include in Flashbacks: No` suppresses surfacing
only; it never deletes historical data.

### Social-media conversations and media — LOCKED

Each person's social conversations are organized by platform, then account or
conversation identity as needed:

```text
Conversations (Social Media chats)/
└── WhatsApp/
    └── main_account/
        ├── Chats/
        │   └── 2026-09-14.md
        └── Media/
            ├── IMG-20260914-WA0012.jpg
            └── IMG-20260914-WA0012.md
```

There is one Markdown chat file per source/platform-local calendar day named
`YYYY-MM-DD.md`. Individual messages retain timestamps/time zones when known
and a stable internal message ID; source-supported records also retain exact
sender display, canonical sender ID, text, reply, reactions, edited/deleted/
forwarded state, linked media, source/platform identity, and source message ID.
Missing source fields are never invented. Group chats use the same scheme,
mapping known senders to people and unknown senders to unresolved people;
membership never establishes friendship.

Current and historical platform identities are recorded in the person facts so
later exports resolve to an existing person. Re-imports append/update safely
using source/canonical IDs, timestamps, hashes, and deterministic matching; they
record Last Chat Import, Last Source Message, and Last App Update rather than
recreating a lifetime conversation. Proven missing/expired content remains an
explicit unavailable placeholder with its reason.

Chat media is a deliberate storage exception: it stays in that platform
conversation's `Media/` folder with its original filename and same-basename
sidecar. Its sidecar records platform/conversation/account, sender and
canonical ID, sent time, message IDs and surrounding context, original name,
hash, provenance, analysis, visible people, transcript when relevant, and human
notes/corrections. Gallery/travel/person views may reference it but must not
move it into ordinary event media. A camera-roll and social-media version of the
same picture remain separate physical source artifacts because their provenance
and technical metadata can differ; they may be linked as related versions.

Canonical conversation truth is Markdown plus its media. The UI may render an
appropriate WhatsApp/Instagram/Snapchat-like view, but generated HTML is never
canonical. Original export HTML/JSON/media stays untouched in `Raw/` until
canonical extraction has been verified at very high confidence and deletion is
explicitly approved.

### Backups, deletion, and deferrals — LOCKED

Backups restore one consistent generation of the structured state: database,
canonical metadata, and integrity-required files must never be mixed across
dates. Detailed large-media backup policy is **DEFERRED**. Historical truth is
retained by default; archives/tombstones may be necessary, but casual deletion
is not. True duplicate physical files require explicit authorization and a
preserved processing history before deletion.

The intentionally deferred decisions are the map/offline stack,
face-recognition engine/model, Hermes implementation and security/masking, and
detailed large-media backup policy. These are genuine deferrals, not gaps to be
filled by inference.

## Connections is a relationship explorer (React Flow + Dagre)

**Connections** is an exploratory, connection-oriented React Flow view, not a
second family tree. Its deterministic sector placement keeps one **FROM**
person prominent and central; Dagre never dictates a generational layout here.
Maternal context is a compact pale-pink island, paternal context is a clearly
separated pale-blue island, and direct external relationships use neutral space
around/below the origin rather than a boxed branch. The separate **Family Tree**
screen remains the Mermaid genealogy renderer.

The persistent **Relationship Builder** has two session-only zones:

- **FROM** contains exactly one person. It starts as the current perspective
  (normally the configured owner); dropping or setting another person replaces
  it. **Return to My Perspective** restores the configured owner.
- **TO** contains zero or many people. Canvas cards, search results, and the
  immediate-connection list support drag/drop as well as accessible **Set as
  FROM** and **Add to TO** actions. Removing a target changes no stored fact.

With TO empty, the canvas shows only FROM's direct stored or canonical
relationships: parents, children, siblings, spouses/partners, explicit
non-biological parent/child kinds, and direct general relationships. It does
not automatically add distant relatives, friends-of-friends, or arbitrary
branches. Edges retain their semantic styling: biological parent/child is
strong, non-biological parent/child is dashed amber, marriage is violet,
sibling is dotted, and explicit general relationships are dashed teal.

With one or more TO people, the backend returns canonical paths for each
FROM → TO pair (family reasoning comes from the Python family engine; general
links are explicit stored facts). Every returned path remains individually
selectable under its target, subject to the safe limits of `max_depth` 1–30 and
`max_paths` 1–50. Missing intermediates are added to the canvas. FROM and TO
are accented, active intermediates stay readable, and the union of active path
edges is emphasized; surrounding context remains mounted but subtly muted.
Changing TO does not discard that context or perform a disruptive reset.

A multi-hop general/family traversal may be displayed as a **Recorded
connection route**, but it never creates a stored or derived friendship label.
Group membership never implies friendship. Paths are query/display data, not
stored relationship truth; structured path errors remain
`NO_RELATIONSHIP_PATH`, `INVALID_MAX_DEPTH`, and `INVALID_MAX_PATHS`. See
[Documentation/Architecture/relationship-paths.md](Documentation/Architecture/relationship-paths.md).

Person information is available only from the compact **ⓘ** action. Ordinary
node clicks select or reveal a person but do not open information. The drawer
has modular Overview, Relationships, Relationship Paths, Memories, Events,
Photos & Videos, Conversations, Documents, Places / Travel, Groups, and
Journal / Notes tabs. Implemented domains are wired to their real sources;
unimplemented future domains are typed empty boundaries rather than invented
production data. Closing the drawer preserves FROM, TO, selected paths, and
the graph state where technically practical.

### Keyboard navigation

| Key | Action |
| --- | --- |
| Ctrl/Cmd+K | Focus person search |
| V | Set selected person as FROM |
| C | Compare selected person |
| P | Add selected person to TO |
| H | Return to owner perspective |
| Esc | Clear route selection, close the drawer, or exit an overlay |

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

1. Default = the configured owner/focus person referenced by the single
   canonical database (`mohammad_yahya_hussain`).
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

- Every person has exactly one folder under
  `People/<primary-group>/<id>/journal(personal thoughts).md`.
- `journal(personal thoughts).md` is the authoritative freeform prose source
  (UTF-8, any language); the adjacent facts-and-about file retains structured
  identity information.
- The app reads the file on open and offers **Reload from disk**, so edits in
  VS Code / Obsidian / Notepad appear without a restart.
- Writes are atomic (temp file + `fsync` + rename). If the file changed on
  disk since it was read, the app refuses to overwrite it (`JOURNAL_CONFLICT`)
  and reloads the external version for manual merge.
- Search reads the journals directly; no competing authoritative copy.

## Existing Hermes tooling (current implementation; expansion deferred)

`GET /api/hermes/tools` exposes a small stable catalog; `POST
/api/hermes/run` executes one tool in the current implementation. Hermes
decides intent; the backend
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
No tool exposes SQL, internal paths, or the repository structure. This existing
surface does not authorize the expanded Hermes architecture, new security or
masking policy, or any Hermes implementation work; those remain deferred by the
Master Plan.

## Backups

`Create Backup` in the Backups screen (or the `create_backup` Hermes tool)
snapshots the restore-critical state into `Backups/` (categorized under `Manual/`,
`Automatic/` or `Safety/…`; valid older top-level snapshots remain available as
Legacy). Automatic is a supported category, but scheduling is not configured in
V1. Each new folder has a collision-safe timestamp/UUID/label ID:

- one same-generation canonical database snapshot
- canonical person/context and other integrity-required metadata/files
- `manifest.json` — app/schema version, file list with sizes and SHA-256

Snapshots are fully verified before publication and before restore. Restore first
creates a verified `Safety/Pre-Restore` snapshot, then reversibly switches the
database, People/Journals, and portable Config and rolls all three back on any
failure. These local snapshots contain readable private family data and are never
uploaded or included in release artifacts.

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
npm run legacy:check  # legacy builder audit for the current compatibility dataset
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
Tests always run against a fresh temporary copy of the current compatibility
dataset;
the real database is never mutated by tests. A headless Edge UI smoke test
(`Codebase/Tests/UI/smoke.mjs`) drives the diagram-first acceptance flow
end-to-end against the running dev stack (see `Codebase/Tests/UI/README.md`).
Verified screenshots live in `Documentation/UI-Screenshots/`.

## Supported Platforms

Mosaic is distributed as a self-contained desktop application with no requirement for end users to install Python, Node.js, or Rust:

| Platform | Architecture | Distribution Package | Status |
|---|---|---|---|
| **Windows** | x64 (`x86_64`) | NSIS Installer (`.exe`) / MSI | Locally built and tested |
| **macOS** | Apple Silicon (`arm64`) | `.app` bundle / DMG | Packaged via native CI runner |
| **macOS** | Intel (`x86_64`) | `.app` bundle / DMG | Packaged via native CI runner |
| **Linux** | x64 (`x86_64`) | AppImage / `.deb` | Packaged via native CI runner |

---

## Installation & Launch

### Windows Installation
1. Download the current **Mosaic** installer from `Codebase/Packaging/release/`.
2. Run the installer. It installs the application for the current user without requiring administrator permissions.
3. Launch **Mosaic** from the Start Menu or desktop shortcut.
4. *SmartScreen note*: Development builds are unsigned. If Windows SmartScreen appears, click **More info** -> **Run anyway**.
5. *Uninstall*: Removing the application via Windows Settings / Control Panel completely removes application binaries but **preserves** your relationship data root and database.

### macOS Installation
1. Download the current Mosaic `.dmg` for your Mac architecture.
2. Open the `.dmg` and drag **Mosaic** to your `/Applications` folder.
3. Launch **Mosaic**.
4. *Gatekeeper note*: As open-source development builds are not notarized by Apple, on first launch right-click the app in Finder and choose **Open**, or visit **System Settings -> Privacy & Security** and click **Open Anyway**.

### Linux Installation
1. Download the current Mosaic AppImage (or `.deb` package).
2. Make the AppImage executable.
3. Run the AppImage.
4. *Runtime libraries*: Standard Tauri Linux dependencies apply (`webkit2gtk-4.1` or `webkit2gtk-4.0`, `gtk3`). On Ubuntu/Debian: `sudo apt install libwebkit2gtk-4.1-0 libgtk-3-0`.

---

## Portable Relationship Data

Your family relationship brain is completely decoupled from application binaries. A Data Root created on one operating system can be transferred directly to another without modification:

```text
<Existing Data Root>/
├── Database/
│   └── relationships.db      # one standard SQLite 3 source of structured truth
├── People/
│   └── <Group>/<PersonID>/   # facts/about, journal, memories, chats, documents, face, profile
├── Media/
│   └── Friends and Family/   # canonical ordinary event media
├── Raw/                      # untouched intake until reviewed and approved
└── Backups/
```

### Moving Data Between OSes
1. **Copy the directory**: Copy your relationship data folder (e.g. via flash drive, local network, or archive) to the destination machine.
2. **Open Mosaic**:
   - If this is a first run, select **[Use Existing Data Folder]** and choose the directory.
   - If the app is already configured, switch the active data root via the UI settings or relocate dialog.
3. **Paths and encoding**: All internal references use relative paths (`/`) and filesystem-safe person IDs. Markdown journals are strictly UTF-8 and tolerate CRLF/LF line endings interchangeably.

### Bootstrap Configuration
The pointer to the active relationship data root is stored in standard OS configuration directories:
- **Windows**: `%APPDATA%\people-relationships\config.json`
- **macOS**: `~/Library/Application Support/people-relationships/config.json`
- **Linux**: `~/.config/people-relationships/config.json` (or `$XDG_CONFIG_HOME/people-relationships/config.json`)

The `people-relationships` configuration path is a deliberately retained
technical compatibility identifier. Existing Data Root folders (including one
named `Family Relationships`) remain valid and are never renamed by Mosaic.

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
npm run legacy:check  # legacy builder audit for the current compatibility dataset
```

---

## Architecture & Detailed Documentation

For in-depth architectural and testing documentation, see:
- [Cross-Platform Packaging Architecture](Documentation/Architecture/cross-platform-packaging.md)
- [Platform Compatibility Matrix](Documentation/Testing/platform-compatibility.md)
- [Data Root Architecture & Safety](Documentation/Architecture/data-root.md)
- [Backup and Restore Design](Documentation/Architecture/backup-restore.md)
- [Relationship Paths & Invariants](Documentation/Architecture/relationship-paths.md)
