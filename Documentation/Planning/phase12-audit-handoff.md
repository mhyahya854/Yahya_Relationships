# Mosaic Phase 12 — Implementation Handoff

Status: **IMPLEMENTED — FINAL SYSTEM AUDIT PENDING.** The current branch tip separates public code from the private Data Root and claims approved Raw files into operation-owned quarantine before copying. Windows uses handle-bound cleanup; macOS and Linux retain the claimed source with an explicit cleanup-pending state when safe identity-bound removal is unavailable. Phase 11 remains frozen and Phase 13 has not started.

Sol's implementation tests, independent Terra and Luna attacks, repair rechecks, full regression, privacy gates, normal push, and remote verification form this phase's gate. Passing it sets **IMPLEMENTED — FINAL SYSTEM AUDIT PENDING**; a separate per-phase independent audit is not required. Historical public commits still contain pre-separation private material. This task sanitizes the current branch tip only; history cleanup is a later dedicated operation, without a force push here.

## What changed

Phase 12 advances only the raw-intake foundation:

- Canonical `Database/relationships.db` migrates atomically from schema 3 to schema 4. The migration creates Raw scan, item, path-history, archive-inventory, duplicate-group/member, proposal, decision, move-operation, and processing-event tables plus lookup indexes.
- A real canonical v3 Data Root must create and verify a `Safety/Pre-Upgrade` snapshot before its v3→v4 DDL. Isolated SQLite fixtures and fresh roots do not generate irrelevant safety snapshots.
- `Raw/` is an empty, open intake area in the Data Root. Scanning walks it recursively without following symlinks, hashes regular files in chunks, detects changed-during-hash sources, continues after errors, and records errors/provenance rather than silently fixing a source.
- SHA-256 exact duplicates are grouped but never collapsed or deleted. A manual Raw rename is reconciled only when there is one unambiguous missing source with the same verified hash and size.
- ZIP inspection reads central-directory metadata only. It never extracts a member and records malformed, unsafe-path, and suspicious conditions.
- The generic classification boundary is intentionally coarse: image, video, audio, document, archive, social/location/phone candidates, folder/container, and unknown. Candidate labels are not parsed facts.
- A human may select one current generic provenance destination under `Database/Sources/`. No media, event, person, relationship, social, or location canonical destination exists in this phase.
- Approval is distinct from moving. The move engine claims the exact source into operation-owned quarantine without replacing an existing path, rehashes it, writes and hashes a staging copy, publishes to an absent destination, and verifies that destination. Windows cleanup is bound to the claimed handle; other platforms retain the quarantined source and surface cleanup pending. Interrupted moves are recovered explicitly.
- Schema 4 already persists operation identity, status, and error details. `CLEANUP_PENDING` uses the existing error field and an operation-ID-derived quarantine path, so the move repair does not silently change schema-4 semantics or require a schema-5 migration. On platforms without identity-bound deletion, a completed move retains its verified source indefinitely; relocation verifies and copies that operation-owned quarantine payload, while unknown or changed payloads block relocation.
- SQLite is authoritative for `raw_processing_history.md`; event markers make the append projection idempotent and a SQLite outbox makes history-write recovery possible.
- Backups include the schema-4 metadata database and history projection, while deliberately excluding `Raw/` binaries. Restore switches the matching history projection with the database/people/config generation or removes a newer projection when restoring an older canonical snapshot.
- The established application shell now has a Raw navigation destination with filters, search, detail/provenance, correction, decision, recovery, and separated approval/move controls. The global Search surface remains unchanged.

## Safety properties to inspect

1. `Raw/` is not silently renamed, moved, deleted, unpacked, or otherwise modified during scan.
2. A hash is not a stable Raw identifier; each discovered source has its own item record and path history.
3. Destination validation forbids absolute/traversal/control/reserved/case-colliding/escaping paths and all overwrite behavior.
4. A source changed after review cannot be approved or moved as if it were the reviewed bytes.
5. Failure cannot prefer destination completion over source preservation. The recovery state is visible and evidence-bearing.
6. History is a human-readable projection, not a second authority.
7. Raw payloads remain outside portable backups and evidence artifacts.

## Verification material

- [Synthetic Raw UI evidence manifest](../UI-Screenshots/Phase12-Raw-Synthetic/MANIFEST.md)
- `Codebase/Tests/Backend/test_phase12_raw_intake.py`
- `Codebase/Tests/UI/raw_e2e.mjs`

Private verification evidence is retained outside public source. The final whole-app adversarial audit remains part of whole-app QA and pre-release, after the implementation phases.

## In-phase verification

Terra independently found that completed cleanup-pending quarantine on macOS and Linux blocked Data Root relocation. The repair verifies and copies the retained operation-owned payload during relocation. Luna independently found that dangling Windows junctions could escape relocation preflight; both nested and top-level runtime links now fail closed before safety-backup creation. Both findings were reproduced with disposable synthetic roots, repaired, and independently rechecked.

The final local regression collected 601 backend tests (598 passed, 3 platform skips); all 12 UI suites passed, including 50 Data Root, 5 Raw, 18 Navigation, and 110 visual checks. A data-free export passed the backend suite and the affected repair tests. Windows desktop check/test, installer build, installed-app persistence and uninstall checks, package audit, and the keyed current-tree privacy gate passed. The Linux package audit permits two exact third-party SVG metadata runs only in the version-matched outer AppImage; changed runs and every other package member still fail the profile-path check. Terra and Luna independently rechecked that exception. The private verification record remains outside public Git.

## Topics for the later final system audit

- [ ] Confirm schema 3 production input receives exactly one verified `Pre-Upgrade` backup before Phase 12 migration.
- [ ] Compare production database/journal/Raw inventories before and after schema migration; the completed run recorded the expected schema-4 Raw metadata structure, one verified safety backup, and an empty history projection.
- [ ] Reproduce scanner behavior with unreadable input, symlink/junction attempts, altered sources, Unicode paths, empty files, malformed ZIPs, nested folders, and case collisions.
- [ ] Reproduce stale proposal, unauthorized destination, occupied destination, and approval-before-current-proposal rejection behavior.
- [ ] Interrupt before source deletion and after destination verification; validate recovery hashes and event/history coherence.
- [ ] Verify backups contain `data/relationships.db` and `data/raw_processing_history.md` at schema 4 but no `Raw/` tree or Raw payload hash manifest entry.
- [ ] Restore schema-4 and schema-3 canonical backups in disposable roots, then validate SQLite integrity, foreign keys, Data Root health, and history-generation consistency.
- [ ] Inspect the browser evidence against the actual controls and repeat the UI flow with a synthetic root.
- [ ] Confirm no deferred processor or Phase 13 behavior has entered the code path.

Later final-system findings require narrow repair and regression verification; this phase does not claim permanent certification.
