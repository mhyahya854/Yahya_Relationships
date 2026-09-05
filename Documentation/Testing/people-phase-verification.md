# Phase 1: People & Person Profile Completion Verification Record

**Phase**: Phase 1 — People + Person Profile Completion  
**Date**: September 2026  
**Repository**: mhyahya854/Yahya_Relationships  
**Starting Commit**: `892b3e2ad882c120cbc31c8a50790af5271ad6ac`  
**Branch**: `main`  

---

## 1. Production Baseline & Integrity Audits

### Baseline Hash & Count Audits (Pre-Implementation)
- **Database Path**: `Database/Main/family.db`
- **Database SHA-256**: `3258C738F9D65B23B15970D0E1E7389E8584A35BA8E26030249061BAF74E096E`
- **Total People Count**: 35
- **Parent-Child Facts**: 44
- **Marriages**: 12
- **Sibling Groups**: 10
- **Derived Focus-Person Cousin Paths**: 21
- **Arbitrary Perspective Kinship Audit**: PASS
- **Active Journals**: 35 canonical `journal.md` files under `Database/People/Family/`
- **Active Orphan Folders**: 0
- **Missing Journals**: 0

### Production Data Safety Guarantee
All automated tests must and do execute using isolated temporary test Data Roots (`tmp_path`). Real production data in `Database/Main/family.db` and `Database/People/` remains immutable and strictly audited before and after test executions.

---

## 2. Implementation Decisions & Architecture

### Backend Architecture
1. **Canonical Person Model**:
   - Single canonical record per real person in `people` table.
   - Support for multiple group memberships in `person_groups` table with one primary group designated for the canonical filesystem folder location (`Database/People/{group}/{person_id}/journal.md`).
   - Group assignment updates preserve canonical journal files without duplicating or overwriting data.
2. **Profile Aggregate Service (`get_person_profile`)**:
   - Aggregates canonical person identity, direct family facts (parents, spouses, children, siblings), general relationships (friends, colleagues, mentors), perspective-aware relationship (primary + additional derived paths computed by Python domain engine), and journal preview in a single high-performance endpoint.
3. **Duplicate Identity Safeguards**:
   - Non-blocking duplicate detection on normalized name, tokens, and aliases.
   - Exposes existing person match details to user with "Open Existing Person" or "Create Anyway" flows.
   - Multiple legitimate same-name individuals remain fully supported with unique generated person IDs.
4. **Safe Removal & Filesystem-Aware Undo**:
   - Consequence preview calculates direct changes, warnings, and derived relationship impacts.
   - Deletion safely archives person journal to `Database/People/_archived/` and records snapshot.
   - Single-step Undo restores database rows and restores archived filesystem folders/journals.

### Frontend Experience
1. **People Directory**:
   - Personal relationship index showing display name, aliases, group badges, and real-time relationship to current perspective.
   - Group filter pills with accurate unique person counts (All, Family, Friends, Colleagues, Other).
   - Real-time client-side and server-side search by name/alias (case-insensitive, supporting Urdu aliases).
   - Useful sorting (Name A-Z, Name Z-A, Birth Year).
   - Empty states and loading skeletons.
2. **Person Profile**:
   - Detailed header with initials avatar, badges, and perspective relationship summary with Urdu support.
   - Preservation of multiple kinship paths (primary + additional paths).
   - Distinction between direct family facts and general relationships.
   - "Show Relationship Path" action seamlessly navigating to the Relationships view with target focused.
   - Tabbed sections: Overview, Relationships, and Journal.
   - In-place Markdown journal reading, editing, and appending with atomic save and disk conflict detection.

---

## 3. Test Execution Record

- **Backend Pytest Suite**: `126 passed, 2 warnings in 35.00s` (`node Scripts/run-py.mjs -m pytest Tests/Backend -v`)
  - Includes 12 dedicated people & profile test cases in `Tests/Backend/test_people.py`: canonical uniqueness, multi-group creation, safe group update without folder duplication, journal preservation, duplicate detection, legitimate same-name people, full profile aggregate endpoint, multi-path preservation, general relationships, delete consequence preview warnings, and filesystem-aware Undo.
- **Legacy Kinship & Perspective Audit**: `PASS` (`npm run legacy:check`)
  - 35 people, 44 parent-child facts, 12 marriages, 10 sibling groups, 21 focus-person cousin paths; arbitrary-perspective checks PASS.
- **Frontend Typecheck**: `PASS` (0 errors) (`npm run typecheck`)
- **Frontend Production Build**: `PASS` (`npm run build`, built in 12.66s)
- **UI / E2E Comprehensive Suite**: `PASS` (`node Tests/UI/people_e2e.mjs`)
  - All 18 verification requirements passed in an isolated sandbox with zero console errors.
- **Cargo Check (Desktop Tauri)**: `PASS` (`cargo check --manifest-path Codebase/Desktop/Tauri/Cargo.toml`, 15.97s)

---

## 4. Production Data Integrity Audits (Post-Implementation)

- **Database Path**: `Database/Main/family.db`
- **Database SHA-256 Match**: `3258C738F9D65B23B15970D0E1E7389E8584A35BA8E26030249061BAF74E096E` (EXACT MATCH)
- **Real Journals Count**: 35 (EXACT MATCH, 100% untouched)
- **Family Facts & Marriages**: 44 parent-child, 12 marriages, 10 sibling groups, 21 cousin paths (EXACT MATCH)

---

## 5. Visual Review & Screenshots

The following real screenshots have been captured, visually inspected, and validated in `Documentation/UI-Screenshots/`:
1. `people-main.png`: People directory displaying canonical unique counts, perspective relationship badges with Urdu labels, search, and sorting.
2. `people-filtered.png`: Filtered view showing group tab filtering.
3. `person-profile.png`: Person Profile header with initials avatar, multiple kinship paths (`paternal first cousin (پہلے کزن)` + `maternal second cousin (دوسرے کزن)`), direct family facts, general relationships, and "Show Relationship Path" action.
4. `add-person.png` / `add-person-dialog.png`: Add Person dialog with duplicate person warning banner ("Open Existing Person" / "Create Anyway"), multi-group selection, and aliases.
5. `edit-person.png`: Edit Person dialog showing multi-group management, primary folder selection, and floating UndoBar.
6. `remove-person-preview.png` / `delete-impact-preview.png`: Safe deletion consequence preview showing direct changes, warnings, and safe archival to `Database/People/_archived/`.

---

## 6. Canonical Journal Integrity Hardening Pass

### Defects Identified
1. **Read Paths Silently Creating Journals / Folders**: Ordinary serialization and read queries (`_person_serialize`, `list_people`, `get_person`, `get_person_profile`, `duplicate_warnings`, `read_journal`) called `db.ensure_person_folder()` or `db.ensure_journal()`, which mutated disk by silently creating folders and blank `journal.md` files whenever a person was accessed. This destroyed missing-journal evidence.
2. **Partial Person Creation on Filesystem Failure**: `create_person()` committed the SQLite transaction prior to creating the folder and journal, and wrapped filesystem operations in `except Exception: pass`, leaving dangling canonical person records without a journal if filesystem creation failed.

### Final Read / Write Separation
- **Read-Only Helpers**:
  - `db.find_person_folder(connection, person_id) -> Path | None`: Resolves canonical directory without touching or creating anything on disk.
  - `db.expected_person_folder(connection, person_id, group_id) -> Path`: Calculates target path without filesystem mutations.
  - `db.find_journal_path(connection, person_id) -> tuple[Path, bool]`: Returns canonical path and boolean existence flag without creating files.
  - `services.journals.read_journal(person_id)`: Uses `_resolve_journal_path_readonly()` and returns `{ "exists": False, "content": "", ... }` if missing on disk.
  - `services.people._person_serialize()`: Exposes `folder`, `folder_exists: bool`, and `journal_exists: bool` purely from read-only lookups.
- **Mutating Helpers (Explicit Write Paths Only)**:
  - `db.ensure_person_folder()` and `db.ensure_journal()`: Reserved exclusively for explicit creation (`create_person`), explicit writes (`save_journal`), and explicit maintenance (`safe_repair_data_root`).

### Missing Journal UX
- **Person Profile (Journal Tab)**: Renders a warning card: *"journal.md could not be found for this person. The canonical Markdown journal file is missing on disk. Reading this profile will not recreate it automatically."*
- **People View**: Badges rows with `⚠` if `journal_exists === false`.
- **Navigation Safety**: Navigating tabs or opening profiles never triggers save or creation operations.

### Create-Person Failure-Atomic Semantics
- Validates request & verifies DataRoot is writable.
- Captures pre-mutation snapshot on undo history.
- Begins SQLite transaction (`BEGIN`).
- Inserts person, aliases, group memberships, and provenance records.
- Attempts `db.ensure_journal()` BEFORE committing SQLite.
- If filesystem creation fails:
  - SQLite transaction is rolled back (`connection.rollback()`).
  - Any partial directory or file created during the attempt is cleanly unlinked/removed.
  - Pre-mutation snapshot is popped from the undo stack (`pop_latest_snapshot()`).
  - Structured `StorageError` (`STORAGE_ERROR`, HTTP 500) is surfaced without being swallowed.
- If filesystem creation succeeds:
  - SQLite transaction commits (`connection.commit()`).
  - Manifest is updated and the new canonical person is returned.

### Regression Tests Added (`Tests/Backend/test_journal_integrity.py` & `Tests/UI/people_e2e.mjs`)
1. `test_existing_person_and_journal_reads_do_not_mutate`: Read paths leave mtime and contents byte-identical.
2. `test_missing_journal_not_recreated_by_reads`: Deleting `journal.md` and executing `list_people`, `get_person`, `check_duplicate_person`, `get_person_profile`, and `read_journal` does NOT recreate the file. Exposes `journal_exists: False`.
3. `test_missing_person_folder_not_recreated_by_reads`: Deleting the person folder leaves it absent on reads. Exposes `folder_exists: False`.
4. `test_explicit_ensure_journal_creates_folder_and_file`: Explicit calls still create folder and file.
5. `test_create_person_normal_success_creates_exactly_one_folder_and_journal`: Normal creation yields 1 folder and 1 journal.
6. `test_create_person_filesystem_failure_rolls_back_atomically`: Mocked filesystem failure rolls back DB, unlinks partial files, pops snapshot, and raises `StorageError`.
7. `test_person_edit_preserves_journal_without_duplication`: Editing a person preserves canonical journal without duplication.
8. `test_create_person_refuses_when_data_root_is_read_only`: Preserves `DataRootReadOnlyError`.
9. `test_cross_platform_spaces_and_unicode`: DataRoots with spaces and Unicode accents function identically.
10. `people_e2e.mjs Step 17b`: UI check ensuring profile displays missing journal warning and leaves disk file absent.

### Production Data Verification
- Production DB SHA-256: `3258C738F9D65B23B15970D0E1E7389E8584A35BA8E26030249061BAF74E096E` (100% UNCHANGED)
- Real Journals: 35/35 (100% UNCHANGED)
- Kinship Baseline: 35 people, 44 parent-child facts, 12 marriages, 10 sibling groups, 21 cousin paths (100% UNCHANGED)

