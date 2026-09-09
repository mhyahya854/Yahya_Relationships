# Data Root Architecture

## Authority and payload

The active Data Root is the single authoritative directory for user data. In a source checkout it may be the repository root, but portable runtime payload is deliberately limited to `Database/` and `Backups/`; source folders such as `Codebase/` and `Documentation/` are never part of a move or restore payload.

```text
<DataRoot>/
├── Database/
│   ├── Main/family.db
│   ├── People/<group>/<person>/journal.md
│   ├── Config/data-root.json
│   ├── Sources/
│   ├── Exports/
│   └── Logs/
└── Backups/
    ├── Manual/
    ├── Automatic/
    └── Safety/
```

Legacy layouts (`data/family.db`, root `family.db`, `people/`, `backups/`, `config/`, and `exports/`) remain readable when their canonical counterpart is absent. Data Root format stays at 1 and application schema stays at 2.

## Bootstrap pointer

The small OS-local bootstrap file selects the active root. It lives at `%APPDATA%\people-relationships\bootstrap.json` on Windows, `~/Library/Application Support/people-relationships/bootstrap.json` on macOS, and `$XDG_CONFIG_HOME/people-relationships/bootstrap.json` (or `~/.config/...`) on Linux. It contains UTF-8 JSON with an absolute `active_root`, `updated_at`, and the root ID when available. It contains no database, Journal, person, or backup data and is not included in portable backups.

Writes use a same-directory temporary file, UTF-8 serialization, flush plus `fsync`, and atomic `os.replace`. A failed write removes only its temporary file and leaves the previous pointer byte-identical. Status reads never rewrite it. Malformed JSON, a non-object value, a missing `active_root`, a wrong type, or an empty path produces `BOOTSTRAP_INVALID`; it is not treated as first run and cannot silently fall back.

`PEOPLE_RELATIONSHIPS_ROOT` is an explicit root override. `PEOPLE_RELATIONSHIPS_BOOTSTRAP` is an authoritative pointer-file override: if that file is absent, the state is `UNCONFIGURED`. Only source development without either explicit override may use the repository fallback.

## State and readiness

The backend exposes `UNCONFIGURED`, `HEALTHY`, `READ_ONLY`, `MISSING`, `INVALID`, `REPAIRABLE`, and `MAINTENANCE`, together with configured status, active/last path, health, read-only and maintenance fields, schema, root format, and root ID. Frontend decisions use these fields rather than English error text.

Backend reachability is independent of Data Root readiness. A reachable backend remains HTTP-ready while the root is unconfigured, missing, or invalid so onboarding and recovery can run. `StartupFailureView` is reserved for an actual backend/process/HTTP failure. Healthy read-only roots open normally with persistent write-disabled status. Safely reconcilable filesystem issues may open as `REPAIRABLE`; repair is an explicit action and never deletes orphan or unknown user content.

Status, health audit, backup inspection, and candidate inspection are read-only. In particular, inspecting a missing path creates no directory, database, Journal, backup, or config file.

## Root-changing transactions

### Create New

Create New accepts only a nonexistent or empty destination and never changes to an existing root. The user supplies their name and may supply a supported gender value; canonical person-ID generation is reused. A hidden sibling staging root is constructed with schema 2, required groups, exactly one owner, owner folder and Journal, focus/default perspective metadata, and Data Root metadata. It is audited and loaded through the family model before publication. The staged directory is renamed to the final target and the bootstrap pointer is committed last. Construction or validation failures remove staging and leave no final root. If the final pointer write fails, the complete inactive root is retained for explicit recovery while the old pointer remains unchanged.

### Use Existing

Candidate inspection verifies directory type, rejects backup snapshots and arbitrary folders, checks SQLite integrity and schema support, performs the complete Data Root audit, and reports counts, identity, format, health, and read-only state without writing. The user reviews this summary and confirms. Switching then holds the maintenance lock, atomically updates the pointer, clears mutation/Undo history, rebinds legacy root paths, and the frontend remounts root-bound perspective and data state. Selecting the active root is a no-op. A healthy read-only root may be selected deliberately; a seriously invalid root may not.

### Restore to a new root

First-run restore always has two explicit locations: the immutable backup source and a separate nonexistent or empty destination. The backup is verified before confirmation. Restore runs inside a sibling staging root under one maintenance lock, is audited and model-validated, then published and activated pointer-last. The source is never used as the live root and remains unchanged. Any pre-publication failure cleans staging; pointer failure preserves the complete inactive result and the previous pointer.

### Move current root

Move first creates and verifies a `Safety/Pre-Organization` backup. It copies only the known runtime payload, excluding source trees, symlinks, SQLite sidecars, staging files, and transient files. Exact relative path, size, and SHA-256 inventory must match before health/model validation, publication, and pointer-last activation. The old root is intentionally retained as a safety copy; the UI states this accurately. Copy, verification, validation, or publication failures clean the unpublished destination and leave the old root authoritative. Pointer failure likewise leaves the old pointer authoritative and retains the fully published inactive copy.

After switch, move, or restore, mutation history is cleared and root-bound legacy paths are rebound. The frontend remounts perspective state and reloads People, Family, Relationships, Search, Journals, and Backups against the new root, preventing Root-A Undo actions or stale identity from affecting Root B.
