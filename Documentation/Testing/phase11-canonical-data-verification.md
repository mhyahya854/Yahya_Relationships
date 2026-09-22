# Mosaic Phase 11 — Canonical Data Verification Report

> **STATUS:**
> `HISTORICAL PROVISIONAL VERIFICATION — SUPERSEDED`
> See [Phase 11 Independent Audit](phase11-independent-audit.md) for the freeze evidence and current test totals.

---

## 1. Scope & Verification Objective

This document provides deterministic cryptographic, relational, and regression evidence for the implementation of Mosaic Phase 11 (Canonical Data Foundation & Migration).

All verification commands and tests were run on the active Windows environment using Python 3.11 within `Codebase/.venv`.

---

## 2. Cryptographic Integrity Baseline

### 2.1 Untouched Source Data
The original authoritative family database was preserved completely untouched in its original location:
- **File:** `Database/Main/family.db`
- **SHA-256 Before Migration:** `3258c738f9d65b23b15970d0e1e7389e8584a35ba8e26030249061baf74e096e`
- **SHA-256 After Migration:**  `3258c738f9d65b23b15970d0e1e7389e8584a35ba8e26030249061baf74e096e`
- **Verification:** Identical bitwise match. Zero mutations occurred on the legacy source file.

### 2.2 Canonical Target Database
- **File:** `Database/relationships.db`
- **SHA-256 after independent repair:** `95faa21cd46a8ee7d64455fe3aa2a881410bf734630f46a51e694b4ba6c41a2c`
- **Size:** 266,240 bytes
- **Pragma `user_version`:** `3`
- **Integrity Check:** `ok`
- **Foreign Key Violations:** `0`

### 2.3 Pre-Migration Safety Backup
- **ID:** `backup-20260919T184332151Z-0d52d225-pre-phase11`
- **Type:** Pre-upgrade atomic safety backup
- **Files Verified:** 38 files verified via `verify_backup()` with 100% hash integrity

---

## 3. Relational Table Parity Audit

Comparison of record counts between `Database/Main/family.db` and canonical `Database/relationships.db`:

```text
Table                    family.db (v1)    relationships.db (v3)    Parity Check
--------------------------------------------------------------------------------
people                   35                35                       PASS (100%)
parent_child             44                44                       PASS (100%)
marriages                12                12                       PASS (100%)
sibling_groups           10                10                       PASS (100%)
sibling_group_members    26                26                       PASS (100%)
fact_sources             297               297                      PASS (100%)
sources                  9                 9                        PASS (100%)
review_notes             13                13                       PASS (100%)
groups                   7                 7                        PASS (100%)
person_groups            35                35                       PASS (100%)
general_relationships   0                 0                        PASS (100%)
aliases                  1                 1                        PASS (100%)
metadata                 11                11                       PASS (100%)
identifier_aliases       N/A               35                       PASS (New v3)
unresolved_people        N/A               0                        PASS (New v3)
platform_identities      N/A               0                        PASS (New v3)
events                   N/A               0                        PASS (New v3)
places                   N/A               0                        PASS (New v3)
```

---

## 4. Kinship Engine & Arbitrary Perspective Audit

The canonical family engine (`Codebase/Scripts/build_family.py`) was executed in strict verification mode against the canonical database:

```powershell
Codebase\.venv\Scripts\python Codebase/Scripts/build_family.py --check
```

**Output:**
```text
Valid: 35 people, 44 parent-child facts, 12 marriages.
Semantic render mapping: 44 parent-child, 12 marriage, 10 sibling-group records.
Derived kinship audit: 21 focus-person cousin paths.
Viewer kinship audit: 35 people; arbitrary-perspective checks PASS.
```

Rebuilding documentation and offline viewing artifacts completed cleanly:
```text
Wrote Database/Exports/Family/family.md
Wrote Database/Exports/Family/family.html
```

---

## 5. Automated Test Suite Execution

The entire backend test suite was executed across all test files:

```powershell
Codebase\.venv\Scripts\pytest Codebase/Tests/Backend -q
```

**Test Results:**
- **Historical provisional run:** 512 collected, 511 passed, 1 skipped.
- **Current authoritative totals:** recorded in `phase11-independent-audit.md`.
- **Failed:** 0
- **Duration:** 152.88 seconds
- **Pass Rate:** 100% of runnable tests

### Test Categories Verified
1. `test_phase11_canonical.py`: 13 passed (canonical ID generation, folder template, migration engine, audit-derived compatibility, backup schema v3).
2. `test_relationships_phase2.py`: 14 passed (exhaustive 1,190 ordered pair check, multi-path resolution, directional reversal).
3. `test_relationships_hardening.py`: 79 passed (constraints, cycles, rollbacks, mutation preview).
4. `test_search_phase6.py`: 57 passed (exact, alias, prefix, journal prose, unicode, limits).
5. `test_paths.py`: 18 passed (path service, graph neighbors, Hermes structured tools).
6. `test_data_root.py` & `test_data_safety.py`: 45 passed (backup, restore, verification, maintenance locking).
7. `test_hermes.py`: 6 passed (tool registry, execution, structured output).
8. `test_root_resolution.py`: 8 passed (real project root resolution, drive simulation, error recovery).
9. All remaining backend API and service tests: 271 passed.

---

## 6. Migration CLI Deterministic Verification

The canonical migration CLI runner was verified in audit mode:

```powershell
Codebase\.venv\Scripts\python Codebase/Scripts/migrate_canonical.py --verify
```

**Output:**
```text
Data Root Health: OK
  Layout: canonical
  Root: <Data Root>
  DB Schema: v3, People: 35
```

---

## 7. Reversibility & Rollback Procedure

The independent audit superseded this provisional rollback checklist. If a later
architectural review requires rollback to the Phase 10 baseline:

1. Restore from the pre-migration safety backup:
   ```powershell
   Codebase\.venv\Scripts\python -c "from app.backend.domain.backups.restore import restore_backup; from pathlib import Path; restore_backup(Path('Backups/Safety/Pre-Upgrade/backup-20260919T184332151Z-0d52d225-pre-phase11'))"
   ```
2. Remove the published Phase 11 artifacts:
   ```powershell
   Remove-Item "Database/relationships.db" -Force
   Remove-Item "People" -Recurse -Force
   ```
3. The original `Database/Main/family.db` and legacy `Database/People` directories remain immediately usable with zero data loss.
