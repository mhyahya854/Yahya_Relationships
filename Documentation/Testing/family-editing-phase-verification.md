# Phase 4 — Family Editing & Mutation UX Verification

## Commit lineage

- Original Phase 4 starting SHA: `284a018111ba151bdc8f23805b9ed201f19e5215` (`Finalize Family focus state and security hardening`).
- Closure starting SHA: `6b7563f18bb79821eba8da91055d7e39485ce04d` (`Implement Phase 4 Family Editing & Mutation UX with safe consequence preview and undo`).
- Final closure SHA: the commit containing this file. Its literal SHA and matching live CI run are recorded in the final handoff because a Git commit cannot contain its own hash: changing this file changes that hash.
- Branch / remote: `main` / `https://github.com/mhyahya854/Yahya_Relationships`.

## Canonical model and UI behavior

Stored facts are the editable source of truth:

- Parent-child: kinds `biological`, `adopted`, `step`, `foster`, `guardian`, `unknown`, `unspecified`; roles `father`, `mother`, `parent`, `unknown`.
- Marriage: statuses `married`, `divorced`, `widowed`, `unknown`; optional year; children status `None` (unspecified), `no_children`, or `unknown`.
- Sibling group: type `None` (default/general) or `full`, plus ordered birth sequence.
- General/non-family connections remain separate stored facts.

Stored facts show their stored classification and expose edit/remove actions. Calculated kinship terms show `Derived Kinship Term` and `Inspect Proof`; they do not expose direct edit or delete controls. To change derived truth, the user edits the underlying stored fact.

The add dialog supports multi-member sibling groups through the canonical `PersonSearch`: the source is always included, additional members appear as removable chips, duplicates are excluded, and at least two total members are required. Default/general groups accept three or more members. A `full` group is limited to exactly two total members and the UI refuses a third selection rather than truncating it.

## Consequence preview architecture

`Codebase/App/app/backend/domain/mutations/preview.py` obtains relationships from the canonical family/path engine. It retains primary stored facts, every distinct path returned by `path_service._derived_paths`, and inferred biological siblinghood where no explicit sibling group exists.

Preview identity is structural, not display-label based. Each derived item carries its canonical path ID plus ordered endpoints, relationship semantics, side, cousin degree/removal, distance, and node chain. Deterministic ordering makes repeated previews byte-for-byte equivalent. Removing one supporting fact can therefore report the affected branch while preserving an independent surviving branch with the same English label. The UI renders side and named path nodes without exposing raw UUIDs.

Preview enforces the same changed constraints as execution, including canonical enums, duplicate parent/marriage/sibling facts, single-person marriage conflicts, ancestry cycles, minimum sibling size, and the two-person full-sibling limit. A preview is an always-rolled-back SQLite transaction.

## Transaction and undo safety

Family mutations use the existing atomic service transaction boundary. Injected failures at the post-write validation seam prove exact rollback for parent-child facts, marriages, and sibling groups. Assertions compare all rows in the mutated tables plus `sources` and `fact_sources`; sibling tests also compare the complete membership table. Each failure leaves the undo stack unchanged. A subsequent valid mutation succeeds and its undo restores the prior domain rows.

The schema remains version 2. This closure adds no migration and changes no production facts.

## Exact backend tests

`Codebase/Tests/Backend/test_family_mutation_ux.py` collects and passes these 18 tests:

1. `test_parent_child_all_seven_kinds_and_undo_cycle`
2. `test_parent_child_refusals`
3. `test_marriage_crud_metadata_and_undo`
4. `test_marriage_refusals`
5. `test_sibling_group_crud_and_derived_persistence`
6. `test_sibling_group_refusals`
7. `test_preview_dry_run_immutability`
8. `test_atomicity_failed_mutation_leaves_undo_clean`
9. `test_read_only_mode_blocks_family_writes`
10. `test_multipath_preview_partial_path_removal_preserves_alternate_path`
11. `test_multipath_preview_is_deterministic`
12. `test_parent_child_injected_failure_rolls_back_exactly`
13. `test_marriage_injected_failure_rolls_back_exactly`
14. `test_sibling_group_injected_failure_rolls_back_members_and_group`
15. `test_multi_member_default_sibling_group_create`
16. `test_full_sibling_group_rejects_more_than_two_members`
17. `test_multi_member_sibling_group_undo_restores_exact_members_and_order`
18. `test_preview_validation_matches_commit_validation`

The multipath tests build two independent cousin branches. Before mutation there are two distinct structural path IDs; previewing removal of one parent-child fact reports only that path ID; execution leaves the alternate relationship intact; undo restores the exact two-path set. Repeating the same preview returns an identical result.

## Family UI E2E coverage

`Codebase/Tests/UI/family_e2e.mjs` passes 65 / 65 mandatory steps. Steps 1–48 retain the committed Family exploration/editing, consequence-preview, undo, refusal, and hostile-name security coverage. Closure steps 49–65 prove:

49. Exactly seven canonical parent kinds are exposed; `adoptive` and `surrogate` are absent.
50. Duplicate family mutation is refused in preview without a save action.
51. Parent-child create runs through preview, save, diagram refresh, and stored-fact rendering.
52. The post-mutation Family focus/target truth is handed to Relationships and the Family session persists on return.
53. Parent-child kind edit changes the stored fact and shows Undo.
54. Undo restores the original parent-child kind.
55. Parent-child delete runs through preview and shows Undo.
56. Undo restores the exact parent-child fact.
57. A full sibling group with more than two members is refused in the UI.
58. A default multi-member sibling group is created through preview and save.
59. Sibling-group ordered metadata is edited.
60. Undo restores the prior metadata.
61. Deleting the new explicit group preserves its separately derived cousin truth.
62. Undo restores the explicit group, followed by isolated-test cleanup.
63. Deleting the canonical Musabiha–Musa stored group falls back to inferred biological siblinghood.
64. Undo restores that exact canonical stored sibling group.
65. Derived kinship still offers `Inspect Proof` and no direct destructive controls.

Marriage create/edit/delete/undo coverage from the original Phase 4 E2E remains green, as do its validation and consequence-preview checks.

## Local verification gates

- Focused backend: `test_family_write.py` 7 / 7; `test_mutations.py` 6 / 6; `test_family_mutation_ux.py` 18 / 18; `test_family_exploration.py` 31 / 31; `test_relationships_hardening.py` 79 / 79; `test_relationships_phase2.py` 14 / 14.
- Full backend: 283 / 283 passed across 22 collected files (greater than the 274-test committed baseline).
- Legacy parity: PASS — 35 people, 44 parent-child facts, 12 marriages, 10 sibling groups, 21 cousin paths, arbitrary perspective.
- Frontend typecheck: PASS.
- Frontend production build: PASS (2,166 modules transformed; only the existing Vite dynamic/static import advisory).
- People UI E2E: 18 / 18 passed.
- Relationships UI E2E: 37 / 37 passed.
- Family UI E2E: 65 / 65 passed.
- Full dev-stack smoke E2E: PASS, all 18 smoke assertions.
- Desktop Tauri crate: `cargo check` from `Codebase/Desktop/Tauri` PASS.

All mutation suites use isolated temporary roots via `PEOPLE_RELATIONSHIPS_ROOT`; no test mutation targets production.

## Production integrity

- `Database/Main/family.db` before and after SHA-256: `3258C738F9D65B23B15970D0E1E7389E8584A35BA8E26030249061BAF74E096E`.
- Canonical journals under `Database/People/Family`: 35 / 35 present and byte-identical.
- No database sidecars or tracked `Database` changes were created.
- Live exact-SHA Build & Package Matrix status and its four release artifact names are reported in the final handoff after publication; this keeps this evidence file from invalidating the SHA it describes.

## Remaining limitation

Sibling-group membership is immutable in place. To add or remove members from an existing group, delete it and recreate it with the desired membership. Multi-member creation, metadata edit, delete, derived fallback, and undo are supported and verified.
