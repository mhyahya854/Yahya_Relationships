# Phase 4 — Family Editing & Mutation UX Verification

## 1. Starting Commit & Baseline
- **Starting Commit**: `284a018111ba151bdc8f23805b9ed201f19e5215` ("Finalize Family focus state and security hardening")
- **Starting Branch**: `main`
- **Remote**: `https://github.com/mhyahya854/Yahya_Relationships`
- **Baseline Family Counts**:
  - 35 people
  - 44 parent-child facts
  - 12 marriages
  - 10 sibling groups
  - 21 focus-person cousin paths
  - 35 canonical journals
- **Production Data Baseline**:
  - `Database/Main/family.db` SHA-256: `3258C738F9D65B23B15970D0E1E7389E8584A35BA8E26030249061BAF74E096E`
  - 35 canonical journals byte-identical.
  - All test runs executed in isolated temporary sandboxes via `PEOPLE_RELATIONSHIPS_ROOT`. Zero mutation of production facts or journals.

---

## 2. Architecture & Design Principles

### Derived vs. Stored Kinship Separation
- **Stored Facts (Ground Truth)**:
  - Parent-child facts (`parent_child` table with 7 distinct relationship kinds: `biological`, `adoptive`, `foster`, `step`, `surrogate`, `guardian`, `unspecified`).
  - Marriages (`marriages` table with statuses: `married`, `divorced`, `widowed`, `separated`, `annulled`, optional `year`, and `children_status`).
  - Sibling groups (`sibling_groups` & `sibling_group_members` tables with type and birth-order sequences).
  - General / non-familial connections (`general_relationships` table).
  - Stored facts display explicit badges (`Stored Fact`, `Parent-Child`, `Marriage`, `Sibling Group`) and provide direct editing and deletion affordances.
- **Derived Kinship (Calculated Truth)**:
  - Kinship terms (such as `cousin`, `aunt`, `uncle`, `nephew`, `niece`, `grandparent`, `grandchild`, `in-law`, `sibling` when inferred through shared biological parents) are derived automatically by the canonical Python relationship engine.
  - Derived relationships display a `Derived Kinship Term` badge and provide an "Inspect Proof" action.
  - Direct edit and removal affordances are disabled or withheld for derived relationships; mutations must occur by editing the underlying stored facts that produce the lineage.

### Safe Mutation Workflow & Consequence Transparency
- **Dry-Run Preview**:
  - Before executing destructive or modifying mutations, dry-run consequence preview evaluates the mutation in an isolated in-memory or rolled-back transaction.
  - Calculates direct fact changes, warnings, and derived kinship consequences (`derived_added`, `derived_removed`).
  - Prohibits invalid mutations (e.g., self-marriage, ancestry cycles, duplicate facts, single-person marriages) with clear blocking error codes without saving.
- **Floating Undo Integration**:
  - Every committed mutation (create, update, delete) records a snapshot onto the mutation stack.
  - Successful mutations surface an accessible `UndoBar` in the UI.
  - Clicking "Undo" invokes the backend undo manager, cleanly restoring prior state and refreshing diagram and relationship panels.

---

## 3. Implementation Details

### Backend Normalization & Services
- `Codebase/App/app/backend/services/family.py`:
  - `add_marriage` & `update_marriage`: Normalized empty strings (`""`) to `None` for optional `children_status`.
  - `add_sibling_group`: Normalized empty strings (`""`) to `None` for `type_`.
- `Codebase/App/app/backend/api/main.py`:
  - Pydantic payload models and endpoints normalized empty string values for `children_status` and `type_` to ensure canonical database representation.
- `Codebase/App/app/backend/domain/mutations/preview.py`:
  - Flexible parameter extraction supporting both `person_a`/`person_b` and `spouse_a`/`spouse_b`, as well as `members`/`member_ids`.
  - Normalized empty strings to `None` across mutation preview routines.
- `Codebase/Tests/Backend/conftest.py`:
  - Ensured mutation undo stack (`_MUTATION_STACK`) is cleared between test fixtures to prevent test cross-contamination.

### Frontend Components & User Experience
- `Codebase/App/Frontend/src/components/PersonDetail.tsx`:
  - Extended `useRelationship` hook to accept `refreshKey?: number | string` in dependency array to allow re-fetching relationship facts after family mutations and undo cycles.
- `Codebase/App/Frontend/src/features/relationships/components/AddRelationshipDialog.tsx`:
  - Supported `MARRIAGE_CHILDREN_STATUSES` and `SIBLING_GROUP_TYPES` with birth-order sequence toggles.
  - Wired Consequence Preview modal on `⚡ Preview Consequences`.
- `Codebase/App/Frontend/src/features/relationships/components/EditRelationshipDialog.tsx`:
  - Added `initialDeleteMode` prop to automatically trigger deletion consequence preview when opened via "Remove Stored Fact".
  - Isolated derived relationship display: shows "Why this term is derived" and underlying lineage paths without edit form inputs or delete buttons.
- `Codebase/App/Frontend/src/views/FamilyView.tsx`:
  - Integrated `EditRelationshipDialog` into Family exploration view.
  - Wired `relRefreshKey` to refresh relationship context whenever a mutation or undo occurs.
  - Added "Edit Stored Fact" and "Remove Stored Fact" context buttons in side panel (disabled for derived relationships).
  - Enhanced `RelationshipListDetailed` with `badge-stored` / `badge-derived` provenance badges, "Edit Stored Fact" / "Remove Stored Fact" for stored entries, and explanatory text + "Inspect Proof" for derived entries.
  - Wired `UndoBar` to display mutation notifications with 1-click Undo restoring previous graph state.

---

## 4. Verification Suite Results

### 1. Backend Mutation UX Suite (pytest)
- **File**: `Codebase/Tests/Backend/test_family_mutation_ux.py`
- **Tests**: 9 / 9 passed.
  1. `test_parent_child_mutation_all_kinds`: All 7 kinds of parent-child relationships (`biological`, `adoptive`, `foster`, `step`, `surrogate`, `guardian`, `unspecified`) persist and validate cleanly.
  2. `test_parent_child_undo_cycle`: Verifies adding, updating, and removing parent-child facts with undo restoration.
  3. `test_marriage_crud_and_normalization`: Empty string normalization for `children_status`, year updates, and undo.
  4. `test_sibling_group_crud_and_inferred_siblinghood`: Verifies explicit sibling group addition and deletion, proving that deleting the explicit group leaves biological siblinghood intact (flipping from stored to derived).
  5. `test_mutation_preview_dry_run_immutability`: Proves preview calculations execute without mutating database state.
  6. `test_mutation_preview_catches_ancestry_cycle`: Verifies preview detects and blocks cycles with code `ANCESTRY_CYCLE`.
  7. `test_mutation_undo_stack_poisoning_prevention`: Ensures failed mutations do not pollute the undo stack.
  8. `test_read_only_mode_blocks_mutations`: Verifies database open in read-only mode rejects mutations with appropriate error codes.
  9. `test_clear_mutation_history`: Verifies undo stack clear semantics.
- **Full Backend Pytest**: 274 / 274 passed (`node Scripts/run-py.mjs -m pytest Tests/Backend -q`).

### 2. Family UI E2E Suite (Puppeteer)
- **File**: `Codebase/Tests/UI/family_e2e.mjs`
- **Result**: 48 / 48 passed.
  - Steps 1–37: Family screen rendering, focus selection, zoom/fit/center, bilingual kinship display, multipath indicators, search, perspective handoff.
  - Step 38: Derived relationship displays "Derived Kinship Term" and "Inspect Proof", with direct editing buttons disabled.
  - Step 39: "Inspect Proof" modal displays lineage path without edit/delete inputs; closes cleanly.
  - Step 40: Stored fact displays "Stored Fact" badge and enabled Edit/Remove affordances.
  - Step 41: Add Family Fact with Consequence Preview, Confirm & Save updates diagram and shows `UndoBar`.
  - Step 42: Undo reverts added fact, diagram updates, and `UndoBar` dismisses.
  - Step 43: Edit Stored Fact updates marriage status, shows `UndoBar`, and undo reverts cleanly.
  - Step 44: Remove Stored Fact displays Consequence Preview, executes deletion, and undo restores fact.
  - Step 45: Ancestry cycle mutation refusal blocks validation in UI preview without save affordance.
  - Step 46: Reset focus to default viewer focus prior to security checks.
  - Step 47: Rendered hostile-name Mermaid DOM is inert (`window.__familyPwned === undefined`, 0 scripts, 0 iframes, 0 inline handlers).
  - Step 48: Browser console has no unexpected errors after hostile-name test.

### 3. Regression & Integration Gateways
- **TypeScript Typecheck**: `npm run typecheck` — 0 errors.
- **Legacy Verification**: `npm run legacy:check` — PASS (35 people, 44 parent-child facts, 12 marriages, 10 sibling groups).
- **People UI E2E**: `npm run test:ui` — 18 / 18 passed.
- **Relationships UI E2E**: `npm run test:relationships` — 37 / 37 passed.
- **Dev Stack Smoke E2E**: `node Scripts/test_e2e_runner.mjs` — All checks passed.
- **Desktop Tauri Crate**: `cargo check --manifest-path Desktop/Tauri/Cargo.toml` — Clean build (`dev` profile).

### 4. Data Safety Verification
- **Production Database**:
  - Path: `Database/Main/family.db`
  - Expected SHA-256: `3258C738F9D65B23B15970D0E1E7389E8584A35BA8E26030249061BAF74E096E`
  - Actual SHA-256:   `3258C738F9D65B23B15970D0E1E7389E8584A35BA8E26030249061BAF74E096E`
  - Status: **100% BYTE-IDENTICAL**
- **Canonical Journals**:
  - Found: 35 journals in `Database/People/Family/`
  - Status: **100% BYTE-IDENTICAL**
