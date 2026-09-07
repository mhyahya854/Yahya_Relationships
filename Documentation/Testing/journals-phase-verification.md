# Phase 5 — Journals Verification

## Baseline and final-SHA convention

- Starting branch: `main`
- Starting `HEAD` and `origin/main`: `dc9a1ea04205dc44fec558d31a7015ccbf5eedaa`
- Production database baseline SHA-256: `3258C738F9D65B23B15970D0E1E7389E8584A35BA8E26030249061BAF74E096E`
- Production Journal baseline: 35 canonical `journal.md` files, each recorded by path, byte length, and SHA-256 before testing.
- Final-SHA convention: the Phase 5 commit that contains this report is the final SHA. Its exact value, matching `HEAD` and `origin/main`, and the exact-SHA CI run are reported in the final handoff because a commit cannot embed its own hash.

## Canonical architecture and authority

- `Database/People/<canonical group>/<person_id>/journal.md` remains the sole authority for Journal prose.
- SQLite remains the authority for structured people, group, and relationship facts. No Journal body column or table was added.
- The database schema was not changed; the application schema contract remains version 2.
- Journal paths are resolved from an existing canonical SQLite person identity and its DataRoot folder mapping. Unsafe IDs are rejected and unknown IDs return a clean not-found error.
- Journal text is decoded and encoded as UTF-8. Saves normalize CRLF and lone CR newlines to canonical LF.

## Revision and conflict contract

Every read returns `person_id`, `exists`, `content`, `sha256`, and `modified_ns`. Saves accept the expected existence state, SHA-256, and modification timestamp.

- Existence changes are conflicts: missing to externally created and existing to externally deleted cannot be silently overwritten.
- SHA-256 is authoritative for content conflicts, including different bytes with the same mtime.
- An mtime-only change with identical bytes is accepted and does not create a false conflict.
- Two writers opened at one revision cannot both save normally; the stale writer receives `JOURNAL_CONFLICT`.
- Normal Save never forces. Force overwrite is available only through the explicit conflict action “Overwrite Disk With My Draft.”
- Conflict responses and a fresh read expose the current disk version while the editor retains the exact local draft. No automatic merge occurs.

## Missing and existing Journal semantics

- Existing empty content (`exists: true`, `content: ""`) remains distinct from a missing file (`exists: false`, `content: ""`).
- `read_journal` and `journal_summaries` are non-creating read paths.
- A missing Journal is created only by explicit Save or Quick Append.
- Conflict checks happen against the non-creating resolved path before the canonical directory or file is created.
- Summary scanning follows canonical database people in deterministic ID order, ignores orphan folders, and skips an unreadable or invalid-UTF-8 Journal without crashing the complete scan.

## Atomic save and external editors

- Saves write a sibling `.journal-*.tmp`, flush it, call `fsync`, and atomically replace `journal.md`.
- Injected write, fsync, and replace failures prove that an existing Journal keeps its exact old bytes, a first save leaves no canonical partial file, and temporary files are removed.
- Reopening always rereads disk. While an editor is mounted, focus triggers a revision check and a four-second poll provides bounded external-editor synchronization.
- A clean editor refreshes to changed disk content. A dirty editor keeps its draft, shows “Changed on disk,” and requires explicit conflict resolution.
- This phase adds no native filesystem watcher and does not claim watcher behavior.

## Shared Journal experience

One `JournalEditor` is used by the embedded Profile Journal tab and the `JournalModal` opened from Family and Relationships (and existing Search routing). It provides:

- View, Edit, Preview, Save, Cancel, Revert, Quick Append, and Reload controls.
- visible Saved, Unsaved, and Changed-on-disk text states;
- `Ctrl+S` / `Cmd+S` save handling with browser-save prevention;
- in-app Keep Editing / Discard guards for dirty cancel, tab switch, modal close, backdrop close, and Escape;
- side-by-side local and disk conflict content with Keep Editing, Use Disk Version, and explicit overwrite;
- accessible labels, dialog roles, keyboard-reachable controls, and `dir="auto"` for mixed-direction text.

Quick Append is an in-app dialog, not `window.prompt`. It accepts optional single-line heading text, defaults to the local `YYYY-MM-DD`, rejects empty entries, normalizes newlines, avoids repeating an existing identical heading, reads the latest disk revision, and is disabled while the main editor is dirty.

The existing React Markdown renderer remains dependency-free and does not use raw HTML injection. Hostile `<script>` and event-handler markup was verified as inert text.

## Focused Journal verification

- Backend: `Codebase/Tests/Backend/test_journals_phase5.py` — 39/39 passed.
- Covered exact UTF-8 reads; CRLF-read normalization with raw-byte hashing; missing read and summary purity; existing, first, and empty saves; English, Urdu, Roman Urdu, mixed text, emoji, LF normalization; default and custom append headings; duplicate-date avoidance; empty append; modification/creation/deletion/two-client conflicts; hash/mtime edge cases; explicit overwrite; no conflict-side creation; three atomic failure points; append race safety; read-only and maintenance refusal; unknown/unsafe IDs; orphan and malformed summaries; absence of SQLite Journal prose; large round trip; and revision updates.
- Dedicated browser suite: `Codebase/Tests/UI/journals_e2e.mjs` — 40/40 passed against a copied temporary DataRoot.
- Browser coverage includes People Profile, Family, and Relationships consistency; exact save/reopen; multilingual content; Preview; keyboard Save; Quick Append; unsaved close choices; clean and dirty external changes; conflict comparison and both resolution routes; large content; hostile Markdown; missing create; external create/delete races; read-only controls; accessibility/direction; and console-error review.

## Frozen regression results

- Full backend: 322/322 passed (includes the 39 Phase 5 tests; frozen baseline was 283).
- People E2E: 18/18 passed.
- Relationships E2E: 37/37 passed.
- Family E2E: 65/65 passed.
- Legacy kinship/perspective audit: passed with 35 people, 44 parent-child facts, 12 marriages, 10 sibling groups, and 21 focus-person cousin paths.
- Frontend typecheck: passed.
- Frontend production build: passed (the existing Vite dynamic/static import warning remains non-fatal).
- Legacy smoke: all 18 reported assertions passed when run with the required dev servers.
- Canonical Tauri `cargo check`: passed from `Codebase/Desktop/Tauri`.

## Production data and visual verification

- Final production database SHA-256 must equal the baseline `3258C738F9D65B23B15970D0E1E7389E8584A35BA8E26030249061BAF74E096E` before commit.
- All 35 production Journal paths, byte lengths, and SHA-256 values must match the stored pre-test manifest before commit.
- The legacy smoke harness uses the configured active root; its generated backup/history artifacts were cleaned and the tracked database was restored to the exact pre-test SHA before the final integrity comparison.
- Visually inspected evidence is limited to the requested three screenshots:
  - `Documentation/UI-Screenshots/journal-view.png`
  - `Documentation/UI-Screenshots/journal-edit.png`
  - `Documentation/UI-Screenshots/journal-conflict.png`
- The screenshots show readable hierarchy, unclipped controls, explicit text status, mixed-language editing, and visible local-versus-disk conflict choices.

## Native CI and artifacts

After the Phase 5 commit is pushed, the `Build & Package Matrix` run for that exact final SHA must finish terminal green for Windows x64, macOS ARM64, macOS Intel x64, and Linux x64. The corresponding four release artifacts must be present. The run ID, per-platform result, and artifact verification are external post-commit facts and therefore belong in the final handoff rather than a self-referential commit document.

## Genuine limitations

- External synchronization is focus plus four-second polling while the editor is mounted, not a native filesystem watcher.
- There is no automatic merge; users deliberately select the disk version or explicitly overwrite it.
- The browser read-only check injects an authentic read-only DataRoot status response to verify disabled controls; backend tests independently exercise real service-level read-only refusal for Save and Append.
- The legacy smoke harness is not itself DataRoot-isolated and requires already-running dev servers; Phase 5’s dedicated Journal E2E is isolated and independently verifies production hashes.
