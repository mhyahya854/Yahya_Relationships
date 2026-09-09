# Phase 7 — Backups and Recovery Verification

## Baseline and final-SHA convention

- Starting branch: `main`.
- `PHASE7_START_SHA`: `51857450fc4b3f6f3312cecab8b36e8c82e2108a` (`Complete deterministic global Search`).
- The starting SHA was clean and equal to `origin/main`.
- Production database baseline: 192,512 bytes, SHA-256 `3258C738F9D65B23B15970D0E1E7389E8584A35BA8E26030249061BAF74E096E`.
- Production prose baseline: 35 canonical `journal.md` files recorded by relative path, bytes, and SHA-256.
- Production Backups baseline: 176 files recorded by relative path, bytes, and SHA-256.
- Final-SHA convention: the Phase 7 commit containing this report is `PHASE7_FINAL_SHA`. Its exact self-referential value and exact-SHA native CI evidence are recorded in the final handoff because a commit cannot embed its own hash.

## Existing architecture audit

The existing domain split (`create`, `manifest`, `verify`, `restore`), DataRootManager portable-path model, process-local maintenance lock, FastAPI router, Tauri open-path bridge, and Backups view/dialog seams were retained. The audit confirmed the category listing mismatch, early final-directory publication, live SQLite `copy2`, permissive manifest/path handling, second-only IDs, in-place restore, missing Config rollback, absent post-health validation, duplicate API routes, browser prompt/alert workflows, and timed simulated progress.

The user-owned historical Safety snapshots were not moved, rewritten, deleted, or used as test targets. Their mixed historical manifest formats are surfaced honestly: valid v1 manifests remain verifiable; incomplete ad hoc manifests remain visible but not restorable.

## Implemented safety contract

- Manual, Automatic, structured Safety reasons, and unchanged Legacy discovery are supported.
- Creation stages on the target filesystem, snapshots SQLite through `Connection.backup()`, rejects symlinks, excludes known temporary files, writes sorted v1 manifests from canonical app/schema metadata, fully verifies, and atomically renames only on success.
- Verification enforces safe portable paths, unique manifest entries, exact file/byte totals, expected-only payload, file size/hash, SQLite integrity/schema, person count, Journal count, required components, and machine-readable compatibility/issues.
- Public Backup endpoints resolve opaque IDs only within recognized active Backups positions.
- Restore requires exact typed confirmation, re-verifies under the maintenance lock, publishes and verifies a Safety/Pre-Restore snapshot, verifies a staged copy, reversibly swaps DB/People/Config, preserves Backups, performs real post-health/family checks, and appends success history only after validation.
- Any failure restores the exact renamed pre-operation bytes for all components already switched. Critical rollback failure is distinct and preserves recovery workspaces.
- Read-only listing/details/verification/open-folder remain available; create and restore are blocked.
- The UI uses in-app create/verify/details/restore surfaces and three truthful client-known restore states. Automatic scheduling is intentionally not implemented.

## Focused automated evidence

- Existing Backup tests: passed.
- Existing Data Safety tests: passed.
- Existing cross-platform portability tests: passed.
- Phase 7 backend suite: 55 checks collected, 54 passed and one capability-based Windows symlink test skipped when symbolic-link creation was unavailable.
- Dedicated Backup browser suite: `npm run test:backups` — 42/42 passed using a copied temporary Data Root and hardened Edge `--edge-skip-compat-layer-relaunch` launch argument.
- The E2E proved category/listing UX, in-app creation, unique IDs, full details/verification, exact DB/Journal/Config restore, verified Safety/Pre-Restore publication, Backups preservation, corrupt refusal, read-only controls, inert hostile labels, and zero unexpected console/page errors.
- UI restore failure injection remains backend-tested; no unsafe production failpoint API was added solely for browser tests.

## Regression, production, native CI, and artifacts

The final local regression evidence is:

- Full backend: 434 collected, 433 passed, one capability-based Windows symlink skip, zero failures (frozen baseline: 379).
- Search focused: 57/57 passed.
- People / Relationships / Family / Journals / Search: 18/18, 37/37, 65/65, 48/48, and 42/42 passed.
- Backup E2E and smoke: 42/42 and 18/18 passed.
- Legacy family audit, frontend typecheck/build, and Cargo check passed.
- Production remained at the exact database hash, the same 35 Journal paths/hashes, and the same 176 Backup files; no sidecar or staging artifact remained.

The final handoff records the exact Phase 7 commit, exact-SHA four-platform native CI/privacy jobs, and the four attached release artifacts after those remote gates reach terminal success.

## Visual verification

Only these four Phase 7 screenshots are authorized and were captured from the isolated E2E Data Root:

- `Documentation/UI-Screenshots/backups-list.png`
- `Documentation/UI-Screenshots/backup-details.png`
- `Documentation/UI-Screenshots/backup-restore.png`
- `Documentation/UI-Screenshots/backup-verified.png`

They are inspected after the shared 150 ms modal fade completes for category clarity, readable timestamps, long/hostile label wrapping, nondominant technical IDs, explicit restore warning, typed confirmation, status text independent of color, and unclipped desktop controls.

## Genuine limitations

- Automatic category support does not include scheduling in V1.
- Backups are uncompressed readable directories; encryption and remote/cloud backup are outside Phase 7.
- Full verification is intentionally I/O-bound because every payload byte is hashed; the current family dataset remains small.
- Backend-unavailable startup recovery cannot call backend restore APIs; the UI does not claim otherwise.
