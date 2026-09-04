# Mutation & Filesystem Consistency Architecture

## Overview
Every state mutation (person creation, person deletion, group relocation) updates structured SQLite data AND filesystem-backed person directories (`Database/People/`) within a unified snapshot manifest.

## Filesystem-Aware Undo History
Reversible mutations track:
1. **Logical database before state**: Snapshot of structured facts and tables.
2. **Filesystem actions**:
   - `created_paths`: Folders or journal files created by the mutation.
   - `moves`: Folders moved to `_archived/` or between primary group directories.

## External Conflict Detection (`UNDO_FILESYSTEM_CONFLICT`)
If a user modifies a person's `journal.md` externally after creation:
- Undoing the creation detects that `journal.md` was modified since snapshot creation.
- The system returns structured error `UNDO_FILESYSTEM_CONFLICT`.
- The modified journal is **NEVER** silently deleted.
- The user can choose to cancel or archive the modified file safely before undoing.

## Deterministic Reconciliation & Repair
The health audit system (`audit_data_root()`) detects:
- `MISSING_PERSON_FOLDER`: DB person exists, folder absent on disk.
- `MISSING_JOURNAL`: Folder exists, `journal.md` missing.
- `ARCHIVED_ACTIVE_MISMATCH`: DB person is active, but folder resides in `_archived/`.
- `ORPHAN_PERSON_FOLDER`: Folder exists on disk, but person absent from DB.

`safe_repair_data_root()` automatically fixes missing folders and journals deterministically, but **NEVER** automatically deletes orphan data.
