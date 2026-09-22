# Mosaic Phase 12 — Independent Audit Handoff

Status: **PROVISIONALLY IMPLEMENTED — INDEPENDENT AUDIT REQUIRED.** Phase 12 is not frozen. Phase 13 is not started or authorized by this handoff.

## What changed

Phase 12 advances only the raw-intake foundation:

- Canonical `Database/relationships.db` migrates atomically from schema 3 to schema 4. The migration creates Raw scan, item, path-history, archive-inventory, duplicate-group/member, proposal, decision, move-operation, and processing-event tables plus lookup indexes.
- A real canonical v3 Data Root must create and verify a `Safety/Pre-Upgrade` snapshot before its v3→v4 DDL. Isolated SQLite fixtures and fresh roots do not generate irrelevant safety snapshots.
- `Raw/` is an empty, open intake area in the Data Root. Scanning walks it recursively without following symlinks, hashes regular files in chunks, detects changed-during-hash sources, continues after errors, and records errors/provenance rather than silently fixing a source.
- SHA-256 exact duplicates are grouped but never collapsed or deleted. A manual Raw rename is reconciled only when there is one unambiguous missing source with the same verified hash and size.
- ZIP inspection reads central-directory metadata only. It never extracts a member and records malformed, unsafe-path, and suspicious conditions.
- The generic classification boundary is intentionally coarse: image, video, audio, document, archive, social/location/phone candidates, folder/container, and unknown. Candidate labels are not parsed facts.
- A human may select one current generic provenance destination under `Database/Sources/`. No media, event, person, relationship, social, or location canonical destination exists in this phase.
- Approval is distinct from moving. The move engine rehashes the current source, writes and hashes a staging copy, publishes to an absent destination, verifies that destination, then removes the source. Interrupted verified moves are recovered explicitly.
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

- [Verification record](../Testing/phase12-raw-intake-verification.md)
- [Raw UI evidence manifest](../UI-Screenshots/Phase12-Raw/MANIFEST.md)
- `Codebase/Tests/Backend/test_phase12_raw_intake.py`
- `Codebase/Tests/UI/raw_e2e.mjs`

The verification record identifies the executed tests, the read-only production baseline, and the completed controlled production upgrade. The final release result adds the final commit and remote verification evidence.

## Independent audit checklist

- [ ] Confirm schema 3 production input receives exactly one verified `Pre-Upgrade` backup before Phase 12 migration.
- [ ] Compare production database/journal/Raw inventories before and after schema migration; the completed run recorded the expected schema-4 Raw metadata structure, one verified safety backup, and an empty history projection.
- [ ] Reproduce scanner behavior with unreadable input, symlink/junction attempts, altered sources, Unicode paths, empty files, malformed ZIPs, nested folders, and case collisions.
- [ ] Reproduce stale proposal, unauthorized destination, occupied destination, and approval-before-current-proposal rejection behavior.
- [ ] Interrupt before source deletion and after destination verification; validate recovery hashes and event/history coherence.
- [ ] Verify backups contain `data/relationships.db` and `data/raw_processing_history.md` at schema 4 but no `Raw/` tree or Raw payload hash manifest entry.
- [ ] Restore schema-4 and schema-3 canonical backups in disposable roots, then validate SQLite integrity, foreign keys, Data Root health, and history-generation consistency.
- [ ] Inspect the browser evidence against the actual controls and repeat the UI flow with a synthetic root.
- [ ] Confirm no deferred processor or Phase 13 behavior has entered the code path.

An audit finding should be fixed narrowly, re-verified, and returned to this provisional state until an independent auditor explicitly approves a freeze.
