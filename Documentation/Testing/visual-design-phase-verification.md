# Phase 10 Visual Design Verification

## Status

**PHASE 10 — TECHNICALLY COMPLETE; HUMAN VISUAL REVIEW REQUIRED.**

This phase establishes a neutral visual foundation and refines every existing application surface. It does not freeze Phase 10, start Phase 11, add Hermes functionality, or implement a future custom theme.

## Immutable start gate

- Branch: `main`
- Required and observed starting commit: `02aa063dde994da1a738773478f9a1002dc00961`
- Starting `HEAD`, `origin/main`, and required commit were identical.
- Starting worktree was clean.

## Visual audit

The pre-change application was structurally sound but visually fragmented. Its strongest inconsistencies were text-glyph navigation icons, a heavy blue active shell, repeated hard-coded cool grays, inconsistent radii and control heights, card borders around nearly every region, over-prominent destructive actions, long paths dominating profile and Data Root views, cramped backup actions, an oversized empty Relationships inspector, and Family focus behavior that scrolled the outer page.

Preserved without redesign:

- all six primary destinations and their navigation/state semantics;
- perspective and contextual-return behavior;
- canonical People, family, relationship, journal, search, backup, and Data Root workflows;
- stored-versus-derived semantics and existing mutation safeguards;
- Urdu/RTL content, ARIA, keyboard behavior, labels, and focus visibility;
- local-first data boundaries and in-app confirmation flows.

## Design system

| Dimension | Phase 10 system |
| --- | --- |
| Color | Warm neutral canvas `#f3f1ec`, paper panel `#fffefa`, ink `#202823`, muted `#68716c`, restrained teal accent `#35695e`, semantic danger/ok/warning colors, and distinct family/general/derived graph colors. |
| Typography | Segoe UI/system stack with Noto Naskh Arabic fallback; compact 14px body, 24px view titles, stronger labels, and readable Urdu line height. |
| Spacing | Compact 4/8/12/16/20/24/32 rhythm, 35–39px controls, and wider view gutters at large sizes. |
| Radii | Shared 7px, 11px, and 16px tiers for controls, panels, and modal/recovery surfaces. |
| Shadows | Quiet panel lift and one stronger floating/modal shadow; ordinary sections rely primarily on spacing and borders. |
| Surfaces | Warm app canvas, paper panels, subtle inset regions, restrained dotted graph canvases, and a dedicated recovery backdrop. |
| Icons | Inline SVG navigation and brand marks; no icon dependency and no semantic behavior change. |

The implementation intentionally reuses the existing CSS architecture and component markup. No theme package, icon package, new state layer, or speculative abstraction was added.

## Surface refinements

- **App shell:** quieter warm sidebar, one clear active marker, compact topbar, SVG navigation, and preserved perspective/return behavior.
- **People/Profile:** clearer table hierarchy, lower-prominence destructive actions, contained long content, calmer identity and perspective cards, and consistent tabs/actions.
- **Relationships:** warm dotted canvas, harmonized semantic edges, restrained nodes/controls/minimap, and a compact empty inspector.
- **Family:** harmonized Mermaid palette, accent focus treatment, consistent controls/panel, and focus scrolling constrained to the diagram viewport.
- **Search:** stronger primary field, quieter result cards, category clarity, and contained bilingual/long result content.
- **Journals:** calm writing surface, consistent toolbar/status hierarchy, and preserved conflict, external-edit, and hostile-markup safeguards.
- **Backups:** compact category rhythm, scannable metadata, aligned actions, restrained restore hierarchy, and refined Data Root panel.
- **Data Root/recovery/startup:** shared recovery surface, readable route hierarchy, consistent fields/statuses, and a refined StartupFailure state.
- **Hermes:** visual tokens were inherited by the existing placeholder only; no functionality was added.

## Synthetic review gallery

Every committed review image was generated from an isolated temporary Data Root containing synthetic people, bilingual aliases, long names, relationships, journals, backups, and recovery states. No production person, journal, backup label, or private production path appears in this set.

| # | Review state | Image |
| --- | --- | --- |
| 01 | People directory | [01-people.png](../UI-Screenshots/Phase10-Review/01-people.png) |
| 02 | Long bilingual person profile | [02-person-profile.png](../UI-Screenshots/Phase10-Review/02-person-profile.png) |
| 03 | Relationship diagram | [03-relationships.png](../UI-Screenshots/Phase10-Review/03-relationships.png) |
| 04 | Selected relationship details | [04-relationship-details.png](../UI-Screenshots/Phase10-Review/04-relationship-details.png) |
| 05 | Family tree | [05-family.png](../UI-Screenshots/Phase10-Review/05-family.png) |
| 06 | Family selected-person inspector | [06-family-selected-person.png](../UI-Screenshots/Phase10-Review/06-family-selected-person.png) |
| 07 | Mixed search results | [07-search.png](../UI-Screenshots/Phase10-Review/07-search.png) |
| 08 | Journal preview | [08-journal.png](../UI-Screenshots/Phase10-Review/08-journal.png) |
| 09 | Backup categories | [09-backups.png](../UI-Screenshots/Phase10-Review/09-backups.png) |
| 10 | Restore confirmation | [10-backup-restore.png](../UI-Screenshots/Phase10-Review/10-backup-restore.png) |
| 11 | Change Data Root | [11-data-root.png](../UI-Screenshots/Phase10-Review/11-data-root.png) |
| 12 | First-run onboarding | [12-first-run.png](../UI-Screenshots/Phase10-Review/12-first-run.png) |
| 13 | Missing-root recovery | [13-missing-root.png](../UI-Screenshots/Phase10-Review/13-missing-root.png) |
| 14 | Read-only state | [14-read-only.png](../UI-Screenshots/Phase10-Review/14-read-only.png) |

All 14 images were manually inspected after the final implementation pass.

## Visual E2E

Command: `npm run test:visual`

Result: **51/51 checks passed.**

The suite creates its own short-path bootstrap and Data Root, seeds 12 synthetic people and representative family/general facts, writes a bilingual hostile-markup journal fixture, creates/restores verified backups, captures the 14 review states, tests `980×640`, `1366×768`, `1440×900`, and `1920×1080`, verifies long-content containment, checks the read-only and missing-root routes, rejects browser dialogs, and proves the production DB, Journals, Backups, and bootstrap remain byte-identical.

The isolated family fixture inserts only canonical `parent_child` and `marriages` rows directly into its temporary SQLite database because the mutation endpoint deliberately runs legacy production-specific semantic audits. The application still computes all displayed kinship and graph behavior through the production engine.

## Frozen regression results

| Gate | Result |
| --- | --- |
| Backend pytest | **493 passed, 1 skipped** (494 collected); 2 dependency deprecation warnings |
| People E2E | **18/18 passed** |
| Relationships E2E | **37/37 passed** |
| Family E2E | **65/65 passed** |
| Journals E2E | **48/48 passed** |
| Search E2E | **42/42 passed** |
| Backups E2E | **42/42 passed** |
| Data Root E2E | **50/50 passed** after rerun; the first attempt reached check 13 then hit a transient Windows `EBUSY` deleting its temporary bootstrap |
| Navigation E2E | **18/18 passed** |
| Smoke journey | **18 reported PASS states** through `Scripts/test_e2e_runner.mjs` against a copied temporary Data Root |
| Legacy family audit | **passed**: 35 people, 44 parent-child facts, 12 marriages, 10 sibling-group records, 21 cousin paths, arbitrary-perspective checks PASS |
| Frontend typecheck | **passed** |
| Frontend production build | **passed** (2,167 modules transformed) |
| Rust | **passed**: `cargo test --locked`; 0 unit/doc tests present, compile and test harness green |
| Diff whitespace | **passed**: `git diff --check` |

## Native desktop verification

A freshly built Windows Python sidecar and the actual Tauri application were launched at the configured `1440×900` size against the retained synthetic bootstrap. This exposed and corrected a packet-boundary bug in the Rust readiness probe: the probe previously read only the first TCP packet and could miss the health-response body. It now reads the complete `Connection: close` response. The relaunched native app passed readiness and loaded synthetic People, groups, state, and relationship graph endpoints.

The repository's ordinary `dev:desktop` shortcut currently resolves its existing `beforeDevCommand` from the repository root and points one directory too high. For this verification only, Vite was started explicitly and Tauri was launched with a transient config override that skipped the duplicate before-dev command; packaged build configuration was not changed.

## Production integrity

The start-of-phase and post-regression inventories match exactly:

| Asset | Before | After |
| --- | --- | --- |
| `Database/Main/family.db` | 192,512 bytes; `3258C738F9D65B23B15970D0E1E7389E8584A35BA8E26030249061BAF74E096E` | exact size/SHA match |
| Canonical Journals | 35 files; per-path size/SHA inventory recorded | all 35 path/size/SHA records exact |
| Backups | 176 files; per-path size/SHA inventory recorded | all 176 path/size/SHA records exact |
| Real bootstrap | 115 bytes; `108506C8E37F9EB38A1ECC8726A2D355C246F3675A3F6774E5BE75AFF8137FDD` | exact size/SHA match |
| Runtime temporary artifacts | 0 | 0 |

The synthetic Data Roots, synthetic bootstrap, baseline-only screenshots, Graphify output, and generated frozen-suite screenshots were removed. The 14 Phase 10 review screenshots are the only screenshot additions intended for staging.

## CI and release contract

The post-push source of truth is the `Build & Package Matrix` workflow for the exact commit containing this file. That workflow must finish 4/4 green, including each platform's mandatory package privacy audit, and publish exactly these artifacts:

- `People-Relationships-Windows-x64`
- `People-Relationships-macOS-arm64`
- `People-Relationships-macOS-x64`
- `People-Relationships-Linux-x64`

The exact workflow run URL, commit SHA, per-platform conclusions, privacy-audit results, and artifact availability are recorded in the final human-review handoff after GitHub finishes the immutable exact-SHA run.

## Human review boundary

Phase 11 has not started. Comprehensive WCAG, screen-reader, global focus-management, reduced-motion, high-contrast, and QoL work remain outside this phase. Existing accessibility semantics were preserved and new visible controls retain keyboard focus and text labels.

Phase 10 must not be marked frozen until the human reviewer accepts the screenshot gallery.
