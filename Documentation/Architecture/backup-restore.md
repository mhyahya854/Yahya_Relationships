# Guided Backup Restore Architecture

## Overview
Backups are complete, verifiable snapshots of the Data Root containing SQLite database state, person folders, Markdown journals, portable config, and a `manifest.json`.

## Backup Structure
Each snapshot folder `backups/backup-<timestamp>-<label>` contains:
- `data/family.db`
- `people/`
- `config/`
- `manifest.json` (declarative SHA-256 file hashes, record counts, and schema versions)

## Pre-Restore Verification
Before restoring any backup:
1. Manifest structure is parsed and validated.
2. Every file's SHA-256 digest is checked against `manifest.json`.
3. SQLite `PRAGMA integrity_check` is executed against `family.db`.

## Mandatory Pre-Restore Safety Backup
Before any active data is modified, an automated pre-restore snapshot (`pre-restore-<timestamp>`) of the current state is created. If the safety backup fails, the restore process aborts immediately.

## Atomic Staged Restore & Rollback
1. Backup is staged in a temporary directory `.tmp_restore`.
2. Staged database and files are validated.
3. Active data root is swapped atomically.
4. Post-restore health check verifies database integrity and filesystem alignment.
5. If any failure occurs during staging or switching, the safety backup is automatically restored.
