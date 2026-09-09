# Phase 8 Data Root / First-Run Verification

## Scope and revision convention

Phase 8 began from `53f95508aae525d2e96da0e0771a4488a6b3b02d` (`Complete atomic backups and verified recovery`). The final Phase 8 SHA is the commit containing this document. Because a commit cannot embed its own SHA, exact evidence is keyed to that SHA in the pushed `Build & Package Matrix` GitHub Actions run and the final handoff.

Application schema remains 2 and Data Root format remains 1. This phase changes bootstrap, onboarding, root selection, move, restore-to-new-root, recovery states, and root-bound invalidation only; it does not start Phase 9.

## Audited defects and contracts

The prior implementation wrote the pointer directly, silently ignored malformed bootstrap content, let an explicit absent test bootstrap fall back to source data, created directories during reads, used a hard-coded owner identity, activated before construction completed, accepted incomplete candidate health, restored without a clearly separate destination, copied source trees during move, published partial destinations, retained cross-root Undo state, and relied on inferred frontend state and timed success.

The final implementation establishes:

- structured states: `UNCONFIGURED`, `HEALTHY`, `READ_ONLY`, `MISSING`, `INVALID`, `REPAIRABLE`, and `MAINTENANCE`;
- backend-service readiness independent of root readiness;
- an OS-local UTF-8 bootstrap pointer written using flush, `fsync`, and atomic replace, with malformed content surfaced as `BOOTSTRAP_INVALID`;
- authoritative explicit bootstrap behavior and pure status/candidate reads;
- inspected and confirmed existing-root switching, including deliberate healthy read-only selection and same-root no-op;
- staged Create New with a user-provided owner, canonical ID generation, schema 2, exactly one initial person, and owner focus/default perspective;
- verified two-location restore into a new staged destination, preserving its backup source;
- runtime-only move with a verified Pre-Organization backup, exact path/size/SHA-256 comparison, root identity preservation, and intentional old-root retention;
- pointer-last publication and failure cleanup for create, restore, and move;
- mutation-history clearing, backend path rebinding, and frontend remount/reload after root changes;
- explicit non-destructive Safe Repair which never deletes orphan folders, unknown Journal content, backups, or unrecognized files.

Backend-free restore is not implemented: onboarding and recovery require the reachable backend service. In browser development the manual path field remains available when the native Tauri folder picker is unavailable. A move deliberately retains the old root for safety.

## Local verification

The Phase 8 focused suite contains 60 passing backend checks. It covers absent and malformed bootstraps, missing/healthy/read-only/corrupt/repairable states, read purity, candidate and backup inspection, pointer flush/replace failures, owner/default/schema invariants, create/switch/restore/move failure injection, unsupported schemas, same-root switching, cross-root Undo isolation, maintenance state, backend readiness, and bounded repair.

The dedicated Data Root browser suite contains exactly 50 passing checks covering genuine first run, the three onboarding routes, owner creation, empty/nonempty destinations, existing-root preview and confirmation, stale-state removal, missing and malformed recovery, separate restore source/destination, backup verification, atomic restore, runtime-only exact-inventory move, old-root retention, repair, read-only signaling, accessibility-relevant labeling/status, and absence of browser dialogs or console errors. It captures only these four reviewed Phase 8 screens:

- `Documentation/UI-Screenshots/first-run.png`
- `Documentation/UI-Screenshots/data-root-existing-preview.png`
- `Documentation/UI-Screenshots/data-root-missing-recovery.png`
- `Documentation/UI-Screenshots/data-root-move.png`

The required frozen verification passed: full backend 493 passed with only the one explicit Windows symlink-capability skip, focused Search 57/57, People 18/18, Relationships 37/37, Family 65/65, Journals 48/48, Search 42/42, Backups 42/42, smoke 18/18, legacy semantic audit, frontend typecheck/build, and Tauri Cargo check. Exact terminal results are also recorded in the final handoff.

## Production integrity and native evidence

Before Phase 8 testing, the production database SHA-256 was `3258C738F9D65B23B15970D0E1E7389E8584A35BA8E26030249061BAF74E096E`; 35 canonical Journal path/size/hash records, all 176 existing Backup path/size/hash records, and the real OS bootstrap bytes were recorded. Phase 8 tests use isolated temporary bootstrap paths. The final gate requires exact equality for all four baselines, clean `Database/` and `Backups/`, and no SQLite sidecars, bootstrap temporaries, staging roots, browser profiles, or test roots in production directories.

After push, the `Build & Package Matrix` run for the exact final SHA is the live proof. It must pass backend pytest, legacy audit, frontend typecheck/build, native Python sidecar, Cargo, desktop packaging, mandatory privacy/security audit, and artifact upload on Windows x64, macOS ARM64, macOS Intel x64, and Linux x64. The corresponding exact-SHA artifacts are `People-Relationships-Windows-x64`, `People-Relationships-macOS-arm64`, `People-Relationships-macOS-x64`, and `People-Relationships-Linux-x64`.
