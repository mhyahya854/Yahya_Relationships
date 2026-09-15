# Phase 10 Visual Design Verification

## Status

**FROZEN FOR LATER REVIEW — technically stable; further whole-app visual review
and refinement is intentionally deferred to the final UI review phase.** Phase
11 has not started. Automated verification is evidence for regression safety,
not permanent final visual approval.

## Scope and authority

- Starting branch and local/remote SHA: `main` at `7181a4e0aa7da4f79c7f2ca67973bf871b591958`.
- The supplied screenshots are visual references only; their example names, paths, dates, IDs, counts, journals, and relationships are not production data.
- The latest graph-first reference supersedes earlier Connections and Family Tree compositions: full dotted workspace, compact nodes, floating perspective/search/dock controls, and a contextual inspector only when a person is selected.
- Connections remains React Flow with deterministic Dagre layout. Family Tree remains driven by the canonical Python family engine.
- No new UI, icon, state, theme, or animation dependency was introduced.
- Hermes is documented and visually aligned only; no new Hermes capability was implemented.

## Corrected relationship architecture

- The current perspective remains the central person. Selecting targets never silently replaces it; `Make central` is an explicit action.
- Targets use independent, removable cards. Multiple targets and multiple selected proof paths form a union on the same canvas.
- Each target shows one canonical primary relationship and the count of additional valid relationships. `Show all relationship paths` is off by default.
- Path checkboxes are independently selectable. Removing one target leaves every other target and path state intact.
- Canonical display ranking is direct family, blood-derived, affinal-derived, then general. A spouse therefore outranks a cousin identity while the cousin path remains available.
- Maternal and paternal routes use pale pink and pale blue respectively and may coexist; a mixed route is never represented by a fabricated blended color. General links remain neutral.
- Marriage is a spouse-to-spouse union. Shared children descend from the union junction. An incoming ancestor line terminates at the exact person node, never at a union container.

## UI refinement

- Added a persistent collapsible sidebar with readable icon-only state and responsive capture coverage at 980, 1366, 1440, 1500, and 1920 px widths.
- Replaced panel-heavy Connections composition with a graph-first canvas, slim 310–348 px contextual explorer, compact bottom dock, collapsed search, and on-demand legend.
- Standardized portal dialogs, backdrop treatment, focus capture/restore, close controls, semantic icons, bilingual/long-name containment, fields, pills, radii, elevation, and alignment.
- Added restrained transform/opacity motion for dialogs, inspector entry, target-card disclosure, sidebar collapse, and interactive feedback. Reduced-motion and reduced-transparency fallbacks are present.
- Light and Dark modes cover shell, graphs, nodes, edges, dialogs, journals, recovery, errors, backup flows, and disabled/focus states without automatic inversion.

## Synthetic fixture and privacy

The deterministic visual fixture contains 52 fictional people over at least five generations, 12+ marriages, 10 sibling groups, supported parent kinds, bilingual and long labels, general relationships, mixed journals, backups, recovery states, and a woman with simultaneous maternal-aunt, paternal-aunt, Chachi, and Mami routes. It is created in an isolated temporary Data Root, validated before capture, and removed afterward. No production identity, journal, backup label, ID, or private path is intentionally placed in the final review package.

## Verification matrix

| Gate | Result |
| --- | --- |
| Frontend typecheck | PASS |
| Frontend production build | PASS; 2,169 modules transformed; known Vite import-mode warning only |
| Rust | `cargo check --locked` PASS; `cargo test --locked` PASS |
| Backend pytest | 498 passed, 1 skipped; 2 dependency deprecation warnings |
| People E2E | PASS |
| Connections E2E | 37/37 PASS |
| Family E2E | 65/65 PASS |
| Journals E2E | 48/48 PASS |
| Search E2E | 42/42 PASS |
| Backups E2E | 42/42 PASS |
| Data Root E2E | 50/50 PASS |
| Navigation E2E | 18/18 PASS |
| Isolated smoke | 17/17 named workflow checks PASS |
| Legacy family audit | PASS: 35 people, 44 parent-child facts, 12 marriages, 10 sibling groups, 21 cousin paths, 35 arbitrary perspectives |
| Phase 10 visual suite | 124/124 PASS |
| Control manifest | 238 discovered, 238 covered, 0 skipped, 0 failures |
| Windows native package | PASS, including staged-bundle privacy audit |

The visual suite explicitly asserts that maternal/paternal path nodes remain on-canvas after viewport focus, multi-target nodes remain visible, target removal is isolated, hostile journal content stays inert, themes persist, active dialogs respond to theme changes, responsive layouts remain usable, and production state is unchanged.

## Final review package

- Directory: [Phase10-Final-Review](../UI-Screenshots/Phase10-Final-Review/README.md)
- Contents before ZIP creation: 174 PNG screenshots plus 1 README; 31,553,146 uncompressed bytes.
- Required numbered areas `00` through `16` are present, including Light/Dark, modal, error, recovery, responsive, control-state, and reference-comparison evidence.
- Key graph captures: `03-connections/full-graph-default.png`, `maternal-paternal-paths.png`, `multiple-targets.png`, `target-removal-isolated.png`, and `04-family-tree/tree-default.png`.
- Motion implementation and reduced-motion evidence: [phase10-motion-evidence.md](phase10-motion-evidence.md).
- Archive: 175 entries, 30,833,690 bytes, SHA-256 `12A7DE6F997458C6ABA59D44FC771FAE0B7D6BBF465D99E7C74753F35F7A941C`; full evidence is in [phase10-refinement-verification.md](phase10-refinement-verification.md).

## Native Windows package evidence

- Backend sidecar: 16,939,524 bytes; SHA-256 `6E4EAB1AE95C86F7891E9F1C929BBAA5D3A6E7146266DD542ECA016A5ADB46C5`.
- MSI 0.5.0: 20,725,760 bytes; SHA-256 `D635D8B0EF2178BEAB99AA32FFC9F24A83BC044FDB3755A9F1F4B0994A0DF512`.
- NSIS 0.5.0: 19,803,804 bytes; SHA-256 `1A933FAEACC276377C681FC68C871770DCE576CACD7E80F1AC578D625E0A1D48`.
- The packaging pipeline built the frontend, sidecar, Tauri application, MSI and NSIS installers, then audited six staged bundle items with zero private-data findings.
- Generated sidecars, installers, targets, and release manifests are build output and are excluded from the source commit.

## Production-integrity boundary

The immutable baseline to recheck immediately before commit and after all tests is:

| Asset | Baseline |
| --- | --- |
| `Database/Main/family.db` | 192,512 bytes; SHA-256 `3258C738F9D65B23B15970D0E1E7389E8584A35BA8E26030249061BAF74E096E` |
| Journals | 35 files; 492 bytes; manifest digest `D2C924C00F59E78842A0F2626BA3BAD456B0EA887957C386C2488C72AA57BC51` |
| Backups | 176 files; 6,147,302 bytes; manifest digest `D354C077062A4EFDD97BDA3963F911E2145A8888F8F6E6605E2DE6C5A6E683DA` |
| Real bootstrap | 115 bytes; SHA-256 `108506C8E37F9EB38A1ECC8726A2D355C246F3675A3F6774E5BE75AFF8137FDD` |

Final exact-SHA remote CI, artifact availability, platform privacy conclusions, and final production-integrity proof are added only after commit and push.

## Research and phase boundary

- Web research used: **No**. External sources or copied implementation proposals: **None**.
- Gallery/media architecture, profile-picture storage, and every Phase 11 item remain unstarted.
- Phase 10 is frozen for later review, not permanently visually approved. The
  dedicated whole-app UI review in Phase 21 explicitly unfreezes the UI after
  the major remaining feature phases.
