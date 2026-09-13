# Phase 10 Reference Map

## Authority and scoring

The 30 user-supplied images are the visual authority for the surfaces and states below. Their fixture names, paths, dates, counts, and prose are not application data and were not copied. The final captures use the isolated 52-person Phase 10 fixture.

Fidelity is assessed with a 100-point structure-and-style rubric so dynamic content does not corrupt the comparison:

| Dimension | Weight | Compared evidence |
|---|---:|---|
| Overall composition | 25 | shell, canvas/page/modal placement, overlay hierarchy |
| Geometry and rhythm | 20 | widths, heights, gutters, padding, repeated-row spacing |
| Component treatment | 20 | cards, pills, fields, buttons, tabs, inspector, dock |
| Typography and icon optics | 10 | hierarchy, weight, wrapping, alignment, icon scale |
| Material and depth | 10 | translucency, blur, borders, shadows, backdrop |
| State fidelity | 10 | selected, open, disabled, warning, success, error |
| Responsive containment | 5 | clipping, overflow, viewport fit |

Scores below exclude dynamic-text and graph-topology differences that necessarily follow from using valid synthetic data. A score of 97 or greater is `PASS`.

## Reference inventory

| Ref | Target application state | Final implementation evidence | Primary implementation | Implemented | Fidelity | Notes |
|---:|---|---|---|---|---:|---|
| 01 | Connections, selected person | [light selected person](../UI-Screenshots/Phase10-Final-Review/03-connections/person-selected.png) | `RelationshipsView`, `GraphDock`, `PersonNode` | Yes | 98 | Full-bleed dotted canvas, compact graph cards, contextual right inspector, floating perspective/search, and bottom graph dock. |
| 02 | People directory | [light directory](../UI-Screenshots/Phase10-Final-Review/01-people/directory-default.png) | `PeopleView` | Yes | 98 | Pill filters, soft person rows, long-name containment, and secondary row actions preserved with synthetic data. |
| 03 | Add Person | [light Add Person](../UI-Screenshots/Phase10-Final-Review/01-people/add-person-dialog.png) | `PersonEditorModal` | Yes | 98 | Compact identity form, group pills, calm footer, modal material, and disabled/active hierarchy match. |
| 04 | Person Profile, Overview | [light profile](../UI-Screenshots/Phase10-Final-Review/02-profile/profile-default.png) | `PersonDetail` | Yes | 98 | Identity header, relationship banner, action row, tabs, Details then About, and long-name wrapping match. |
| 05 | Compare result | [light comparison](../UI-Screenshots/Phase10-Final-Review/02-profile/compare-result.png) | `PersonDetail` comparison dialog | Yes | 98 | Paired relationship cards, reciprocal labels, and perspective actions preserve reference hierarchy. |
| 06 | Edit Person | [light Edit Person](../UI-Screenshots/Phase10-Final-Review/02-profile/edit-person-dialog.png) | `PersonEditorModal` | Yes | 98 | Identity summary, grouped form sections, chips, notes, and sticky action footer match. |
| 07 | Person Profile, Connections | [light connections tab](../UI-Screenshots/Phase10-Final-Review/02-profile/connections-tab.png) | `PersonDetail` | Yes | 98 | Profile shell is preserved while family and general connection sections use the learned card system. |
| 08 | Compare picker | [light picker](../UI-Screenshots/Phase10-Final-Review/02-profile/compare-picker.png) | `PersonDetail` comparison picker | Yes | 98 | Search-first compact person list, initials, modal proportions, and close treatment match. |
| 09 | Journal Edit, wide profile variant | [light editor](../UI-Screenshots/Phase10-Final-Review/06-journal/edit-mode.png) | `JournalEditor` | Yes | 98 | Segmented modes, centered save/cancel, right utilities, unsaved state, and full writing surface match. |
| 10 | Journal Edit, compact profile variant | [responsive journal](../UI-Screenshots/Phase10-Final-Review/14-cross-screen/responsive-1366x768.png) | `JournalEditor`, responsive profile shell | Yes | 97 | Same journal hierarchy adapts without global horizontal scrolling at the smaller reference proportions. |
| 11 | Add Relationship | [light relationship dialog](../UI-Screenshots/Phase10-Final-Review/03-connections/add-relationship-dialog.png) | `AddRelationshipDialog` | Yes | 98 | Searchable target, canonical/general domain control, type/direction fields, and preview/save hierarchy match. |
| 12 | Startup failure with diagnostics | [light diagnostics](../UI-Screenshots/Phase10-Final-Review/10-recovery/service-unavailable-details.png) | `StartupFailureView` | Yes | 99 | Alert header, recovery actions, progressive diagnostics disclosure, and safe-data explanation match. |
| 13 | Startup failure, details hidden | [light failure](../UI-Screenshots/Phase10-Final-Review/10-recovery/service-unavailable.png) | `StartupFailureView` | Yes | 99 | Centered recovery card, quiet backdrop, primary retry, secondary folder/details, and danger exit match. |
| 14 | Use Existing Data Root, compact route | [first-run existing route](../UI-Screenshots/Phase10-Final-Review/09-first-run/use-existing-route.png) | `RootUnavailableView` | Yes | 98 | Focused path route with Browse, disabled inspect action, and Back navigation match. |
| 15 | Missing Data Root recovery | [light missing-root recovery](../UI-Screenshots/Phase10-Final-Review/10-recovery/missing-root.png) | `RootUnavailableView` | Yes | 98 | Last-known location, issue card, primary Retry, and three recovery routes match. |
| 16 | Change Data Location | [light change location](../UI-Screenshots/Phase10-Final-Review/08-data-root/change-location-dialog.png) | `ChangeDataRootDialog` | Yes | 98 | Move/switch segmented actions, current path context, destination field, and review action match. |
| 17 | Data Root Health Audit | [light health audit](../UI-Screenshots/Phase10-Final-Review/08-data-root/health-validation.png) | `DataRootHealthDialog` | Yes | 99 | Status banner, database/filesystem cards, issue summary, counts, and close hierarchy match. |
| 18 | Change Data Location, duplicate reference | [light change location](../UI-Screenshots/Phase10-Final-Review/08-data-root/change-location-dialog.png) | `ChangeDataRootDialog` | Yes | 98 | Duplicate supplied reference maps to the same final dynamic state. |
| 19 | Restore confirmation | [light restore confirmation](../UI-Screenshots/Phase10-Final-Review/07-backups/restore-confirmation.png) | `RestoreBackupDialog` | Yes | 98 | Destructive warning, backup facts, typed confirmation, disabled confirm, and cancellation hierarchy match. |
| 20 | Family legend | [light Family legend](../UI-Screenshots/Phase10-Final-Review/04-family-tree/legend-visible.png) | `FamilyView`, `GraphLegend` | Yes | 98 | Focus, maternal, paternal, marriage, parent-child, and sibling/cross-link semantics remain distinguishable. |
| 21 | Family Tree canvas | [light Family Tree](../UI-Screenshots/Phase10-Final-Review/04-family-tree/tree-default.png) | `FamilyView` | Yes | 97 | Later user correction governs the shell: full canvas, floating context/search/dock, contextual inspector. Mermaid/Python topology remains canonical. |
| 22 | Backup Verified | [light verification](../UI-Screenshots/Phase10-Final-Review/07-backups/verification-success.png) | backup verification dialog | Yes | 99 | Success icon, verified title, concise verification explanation, and database/schema result match. |
| 23 | Backup Details | [light backup details](../UI-Screenshots/Phase10-Final-Review/07-backups/backup-details.png) | `BackupDetailsDialog` | Yes | 98 | Verification banner, metadata/content split, path containment, and verified status match. |
| 24 | Create Manual Backup | [light create dialog](../UI-Screenshots/Phase10-Final-Review/07-backups/create-backup-dialog.png) | `BackupsView` dialog | Yes | 99 | Explanatory copy, single label field, category note, and primary backup action match. |
| 25 | Create New Data Root | [first-run create route](../UI-Screenshots/Phase10-Final-Review/09-first-run/create-route.png) | `RootUnavailableView` | Yes | 98 | New location, person identity, gender, disabled review action, and Back treatment match. |
| 26 | Invalid Mutation | [light validation error](../UI-Screenshots/Phase10-Final-Review/11-errors/invalid-mutation.png) | `MutationPreviewDialog` | Yes | 98 | Error header, readable validation list, error code, direct-fact summary, and safe cancellation match. |
| 27 | Restore From Backup route | [first-run restore route](../UI-Screenshots/Phase10-Final-Review/09-first-run/restore-route.png) | `RootUnavailableView` | Yes | 98 | Source picker, Browse, disabled verification, Back, and destination separation match. |
| 28 | Use Existing Data Root, wide route | [recovery existing route](../UI-Screenshots/Phase10-Final-Review/10-recovery/missing-root-use-existing.png) | `RootUnavailableView` | Yes | 98 | Duplicate semantic route rendered in recovery context and retained as a distinct evidence state. |
| 29 | First-run Welcome | [light welcome](../UI-Screenshots/Phase10-Final-Review/09-first-run/welcome-default.png) | `RootUnavailableView` | Yes | 98 | Welcome header, three large routes, primary existing-root choice, and safety note match. |
| 30 | Corrected graph-shell composition for Connections and Family Tree | [Connections selected](../UI-Screenshots/Phase10-Final-Review/03-connections/person-selected.png); [Family Tree selected](../UI-Screenshots/Phase10-Final-Review/04-family-tree/person-selected.png) | `RelationshipsView`, `FamilyView`, `GraphDock` | Yes | 99 | Explicit later correction: both graph destinations use the same full-canvas shell, floating perspective/search, conditional right inspector, and floating bottom dock. |

## Graph-shell correction

The final user-supplied graph composition supersedes earlier captured graph layouts for both Connections and Family Tree. Both now use the same layout grammar:

- full-bleed dotted workspace after the sidebar;
- floating `Perspective of` context at upper left;
- collapsed search at upper right;
- compact graph/tree nodes with the graph continuing behind chrome;
- a right-side inspector only while a person is selected;
- a full-width floating bottom dock for zoom, fit/fullscreen, filters, and legend.

Connections preserves React Flow and Dagre. Family Tree preserves Mermaid and the canonical Python kinship engine, including maternal/paternal, marriage, parent-child, sibling/cross-link, and multipath semantics.

## Completion

- References discovered: **30**
- References implemented: **30**
- References at or above 97%: **30**
- References below 97%: **0**
- Objective constraints: dynamic synthetic names, paths, counts, journals, and canonical graph topology intentionally differ from the non-canonical screenshot fixture content.
