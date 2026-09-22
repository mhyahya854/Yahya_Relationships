# Mosaic Phase 12 — Raw Intake Verification

Status: **PROVISIONALLY IMPLEMENTED — INDEPENDENT AUDIT REQUIRED.** This is not a Phase 12 freeze, and it does not authorize Phase 13.

## Scope and safety boundary

The verification fixtures are generated only in disposable temporary Data Roots. They use small synthetic PDF-like, JPEG-like, text, binary, ZIP, Unicode-path, duplicate, renamed, missing, changed, and intentionally malformed archive inputs. No personal file under the active Data Root was copied into a test fixture.

The implementation records Raw inventory and processing events in canonical SQLite schema 4 and projects those events to `Database/raw_processing_history.md`. It does not unpack an archive, parse a social export, create a media/event/location/identity fact, send data remotely, or delete an exact duplicate.

The only Phase 12 move target is a human-selected path beneath `Database/Sources/`. The move engine creates a verified staged copy, publishes it only if the final path is absent, rehashes the published file, and deletes the Raw source only afterwards. A failure after destination verification leaves both byte-identical copies and requires an explicit recovery action.

## Production baseline recorded before migration

At `2026-09-22T16:33:45Z`, the active production database was read-only inspected as schema 3 with `PRAGMA integrity_check = ok`, zero foreign-key violations, 35 people, no `raw_items` table, and an empty `Raw/` directory.

| Artifact | Bytes | SHA-256 before Phase 12 migration |
| --- | ---: | --- |
| `Database/relationships.db` | 266,240 | `95faa21cd46a8ee7d64455fe3aa2a881410bf734630f46a51e694b4ba6c41a2c` |
| `Database/Main/family.db` | 192,512 | `3258c738f9d65b23b15970d0e1e7389e8584a35ba8e26030249061baf74e096e` |

## Controlled production migration result

The active root was then migrated once from schema 3 to schema 4. Before its DDL, Mosaic created the verified snapshot `Backups/Safety/Pre-Upgrade/backup-20260922T164714792Z-afa55e99-before-phase-12-schema-upgrade`. Its manifest verifies as schema 3 and contains no `Raw/` payload.

Post-migration, `PRAGMA integrity_check = ok`, foreign-key violations remain zero, metadata and `PRAGMA user_version` are both `4`, all ten `raw_*` authority tables exist, the newly created empty `Raw/` directory contains zero files and zero recorded items, and the history projection contains only its authority header.

| Artifact | SHA-256 after controlled migration | Outcome |
| --- | --- | --- |
| `Database/relationships.db` | `82e7876fcc27580dfc0008171b1d9e4d9a671f3dd87a85a7c500bc297138832e` | Expected schema-4 metadata change. |
| `Database/Main/family.db` | `3258c738f9d65b23b15970d0e1e7389e8584a35ba8e26030249061baf74e096e` | Unchanged from baseline. |
| `Database/raw_processing_history.md` | `78d51168c4275de4d30d3c2696ca7305a269cf0fe39aaaaeb36ed1ce39d0d992` | New empty authority projection; no personal Raw event exists. |

## Executed verification

| Command | Result | What it covers |
| --- | --- | --- |
| `Codebase/.venv/Scripts/python.exe -m py_compile Codebase/App/app/backend/db.py Codebase/App/app/backend/domain/raw_intake.py Codebase/App/app/backend/api/routes/raw.py Codebase/App/app/backend/domain/backups/create.py Codebase/App/app/backend/domain/backups/restore.py` | Passed | Syntax for schema, intake, API, backup, and restore changes. |
| `Codebase/.venv/Scripts/python.exe -m pytest Codebase/Tests/Backend/test_phase12_raw_intake.py -q` | Passed: 10 tests | v3→v4 atomic migration, verified pre-upgrade snapshot, streaming scan, classification, archive metadata-only handling, duplicate retention, rename/missing history, stale approval rejection, overwrite/traversal rejection, move recovery, history outbox, and backup/restore behavior. |
| `npm --prefix Codebase/App/Frontend run typecheck` | Passed | Raw view, navigation, and data-root schema wording compile under the existing TypeScript project. |
| `npm --prefix Codebase run test:raw` | Passed: 5 checks | Real browser workflow against a disposable Data Root, with byte-for-byte before/after Raw fixture comparison and production-tree comparison. |

The browser test emits the focused evidence set listed in [Phase 12 Raw UI manifest](../UI-Screenshots/Phase12-Raw/MANIFEST.md). It covers empty state, results, duplicates, blocked media, correction, approval/no-move explanation, ready-to-move, completed move, and dark mode.

## Acceptance evidence mapping

| Requirement | Evidence |
| --- | --- |
| Raw inventory is separate from content hash and retains path history | `raw_items`, `raw_item_paths`, and `test_missing_and_rename_reconciliation_preserve_history`. |
| Scan does not mutate source material | Scanner uses `os.scandir`, non-followed links, chunked SHA-256, and the browser test compares synthetic Raw hashes before/after scan. |
| Duplicate handling never deletes automatically | SHA-256 groups retain one member row per source; unit and browser tests assert two retained copies. |
| Archive handling is metadata-only | ZIP `infolist()` metadata test includes malformed input and asserts no extracted member appears. |
| Approval is explicit and stale-state safe | `raw_proposals`, `raw_decisions`, current source rehash at approval/move, and the approval modal evidence. |
| Move ordering prevents source loss | `raw_move_operations`, staged copy/hash/publish/hash/delete ordering, injected failure recovery test. |
| Markdown history is recoverable | SQLite outbox plus idempotent event markers; outbox failure test and backup/restore test. |
| Backup excludes Raw binary payload | Backup test asserts metadata/history inclusion and no `Raw/` payload in snapshot. |

## Deliberately deferred

- Content galleries, image/video/audio viewers, OCR, transcripts, summaries, tagging, and embeddings.
- Event construction; people, relationship, place, or identity inference; face recognition; social-export parsing; phone-backup import; location extraction.
- Archive extraction, automatic organization, automatic duplicate cleanup, and any irreversible bulk action.
- Any Phase 13 implementation or a Phase 12 freeze.

## Required independent-audit challenge

An independent reviewer must run the targeted and full regression suites, inspect actual routes and state transitions, verify the production safety snapshot and schema upgrade, and attempt at least the following against a disposable root:

1. Change or replace a Raw source after scan and after approval; confirm no move occurs.
2. Use traversal, absolute, reserved-name, case-collision, symlink/junction, and existing-destination inputs; confirm no write escapes or overwrites.
3. Interrupt every move phase, especially after destination verification; confirm the source remains until explicit recovery can prove both hashes.
4. Restore a Phase 12 backup and a pre-Phase-12 canonical backup; confirm no old history projection is mixed into the restored generation.
5. Confirm a production Raw binary does not enter a backup, a screenshot, a log, or an unintended tracking surface.

Only a successful independent challenge permits a later Phase 12 freeze decision.
