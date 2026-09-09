# Backup and Recovery Architecture

## Snapshot scope and layout

A backup is a local, readable, portable snapshot of the restore-critical Data Root state only:

- `data/family.db`, produced with SQLite's online backup API;
- `people/`, including every canonical person file and `journal.md` byte;
- `config/`, containing portable Data Root configuration; and
- `manifest.json`, containing deterministic metadata, counts, byte sizes, and SHA-256 hashes.

`Backups/`, application code, exports, build products, browser profiles, locks, and temporary files are not snapshot payload. A symbolic link in `People` or portable `Config` blocks creation rather than allowing external files to be followed.

New user snapshots are stored under `Backups/Manual/<backup-id>`. Programmatic safety snapshots use `Backups/Safety/<reason>/<backup-id>`, where the supported reasons are `Pre-Restore`, `Pre-Upgrade`, `Pre-Organization`, and `Pre-Repair`. `Backups/Automatic` is recognized by listing, verification, details, and restore, but automatic scheduling is not configured in V1. Valid pre-category snapshots directly under `Backups/` remain in place and are exposed as Legacy.

Backup IDs contain a millisecond UTC timestamp, a random short UUID, and a portable label slug. The original display label is retained in the manifest.

## Creation transaction

Creation holds the existing process-local maintenance lock, unless it is invoked by an operation that already holds that lock. It checks Data Root writability, builds the snapshot in a hidden staging directory on the destination filesystem, uses `sqlite3.Connection.backup()` for a standalone WAL-safe database, copies People and portable Config without following links, writes a deterministically sorted manifest, and runs full verification. Only a verified staging directory is renamed to its final visible ID. Failure removes staging and never publishes a partial backup.

The format remains backup format v1 and application schema v2. Manifest paths are forward-slash relative paths. `source_root`, when present, is informational only and never controls restore destination.

## Manifest and verification

New v1 manifests require kind, format version, creation time, category/reason, display label, application/Data Root/SQLite schema versions, file and byte totals, people and Journal counts, and a sorted file array of relative path, SHA-256, and byte size. The reader rejects missing keys, unsupported kind/version, empty or duplicate paths, absolute paths, traversal, backslashes, drive syntax, malformed hashes, non-integer or negative sizes, missing `data/family.db`, and inconsistent manifest totals.

Full verification additionally rejects missing, extra, linked, wrong-size, or wrong-hash payload files; requires People and Config components; opens SQLite read-only; runs `PRAGMA integrity_check`; reads schema metadata; compares the schema, person count, and Journal count with the manifest; and returns machine-readable issue codes plus compatibility state. Schema 1 is accepted through the existing migration path, schema 2 is current, and a newer or otherwise unsupported schema is blocked.

Public backup HTTP endpoints accept only an opaque backup directory name. Resolution searches only the recognized active `Backups` category positions and rejects path separators, absolute paths, traversal, missing IDs, and ambiguous IDs. The separate Data Root recovery workflow may accept a user-selected explicit snapshot directory, but it still performs the same strict manifest and payload verification before restore.

## Restore transaction and rollback

Restore requires the exact `RESTORE` token, a writable Data Root, no competing maintenance operation, and a verified compatible source. A corrupt source is rejected before a safety snapshot or active mutation. Under the maintenance lock the source is verified again, then a separately verified current-state snapshot is published under `Backups/Safety/Pre-Restore` before mutation.

The restore source is copied to a hidden same-filesystem workspace and fully verified again. The active SQLite file, People tree, and portable Config tree are individually renamed into one rollback workspace before their staged replacements are renamed into place. `Backups/` is never part of this switch, so the chosen source, safety snapshot, and older backups survive.

After the switch the backend runs SQLite integrity and schema checks, exact expected person count, Journal readability, the full Data Root audit/reconciliation, and the canonical family model validation when a focus person is configured. Only then is a successful entry appended to restored portable Config history. DB connections are request-scoped, and the frontend reloads only after backend success; there is no stale singleton database handle to invalidate.

Any staging, switch, history, or post-health failure restores every switched DB/People/Config component from the exact renamed pre-operation bytes. A normally completed rollback removes temporary work and returns `RESTORE_FAILED`. If rollback itself fails, `RESTORE_ROLLBACK_FAILED` preserves staging, rollback, and the safety backup for manual recovery and does not claim the Data Root is safe.

## Read-only, UI, and recovery boundary

Read-only roots permit listing, details, full verification, and opening canonical folders. Creation and restore are blocked because no safety snapshot can be published. Other app-managed mutations remain blocked by the existing maintenance lock during creation or restore.

The Backups screen separates Manual, Automatic, Safety, and Legacy. Create, verification result, details, and restore confirmation are in-app dialogs; corrupt or incompatible restores are disabled. Restore progress reports only frontend-known states: verification, the active backend safety/restore operation, and confirmed completion. No browser prompt/alert or timed simulated stage is used.

If the backend is running while the configured Data Root is unavailable, the existing recovery view can select and strictly verify an explicit backup into a target root. If the backend itself cannot start or respond, the startup-failure view can only retry, show diagnostics, open the application folder, or exit; it does not claim that a backend-dependent restore is available.

Snapshots contain private family data in readable local files. They are never uploaded, and packaging privacy checks must exclude all production/test `Database`, `People`, and `Backups` content from release artifacts.
