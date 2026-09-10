# Phase 10 Full UI Review

All screenshots were captured at 1440×900 unless the filename identifies a responsive viewport. The suite uses only an isolated synthetic bootstrap and Data Root; no production names, journals, backup labels, or private paths appear in this package.

## Shell

- [perspective-dropdown.png](00-shell/perspective-dropdown.png) — Application-wide Perspective of control with person choices open. Covers: Perspective of; person options; dropdown close.

## People

- [directory-default.png](01-people/directory-default.png) — People directory default with filters, search, sorting, groups, and restrained row actions. Covers: Add Person; filters; search; sort; Profile; Edit; Delete.
- [row-actions-hover.png](01-people/row-actions-hover.png) — People row hover revealing the restrained destructive action. Covers: Profile; Edit; Delete.
- [remove-person-confirmation.png](01-people/remove-person-confirmation.png) — People row Remove confirmation on isolated synthetic data. Covers: Delete; Cancel; confirmation.
- [add-person-dialog.png](01-people/add-person-dialog.png) — Add Person dialog with human identity fields and group choices. Covers: Add Person; Save; Cancel; close.
- [family-filter-selected.png](01-people/family-filter-selected.png) — People directory with Family group selected. Covers: Family filter; All; Clear filters.
- [relationship-sort.png](01-people/relationship-sort.png) — People directory sorted by relationship to the current perspective. Covers: Sort control; Relationship option.
- [search-result.png](01-people/search-result.png) — People directory filtered by an Urdu alias. Covers: Search field; Clear filters; result Profile/Edit/Delete.

## Profile

- [profile-default.png](02-profile/profile-default.png) — Long-name bilingual profile in the locked information order. Covers: Relationship Path; View from; Family Tree; Edit; Compare; overflow; tabs; close.
- [connections-tab.png](02-profile/connections-tab.png) — Profile Connections tab with stored and derived family context. Covers: Connections tab; related-person links.
- [edit-person-dialog.png](02-profile/edit-person-dialog.png) — Profile Edit Person dialog over the preserved profile context. Covers: Edit Person; Save; Cancel; close.
- [compare-picker.png](02-profile/compare-picker.png) — Profile Compare picker with synthetic people. Covers: Compare; person choices; close.
- [compare-result.png](02-profile/compare-result.png) — Profile comparison result with perspective-aware labels. Covers: Compare choice; View from; close.
- [overflow-open.png](02-profile/overflow-open.png) — Profile overflow menu keeping Remove Person out of the everyday action row. Covers: More profile actions; Remove Person.
- [remove-person-confirmation.png](02-profile/remove-person-confirmation.png) — Profile Remove Person confirmation on isolated synthetic data. Covers: Remove Person; Cancel; confirmation.
- [dirty-close-guard.png](02-profile/dirty-close-guard.png) — Profile close guard preserving a dirty Journal draft. Covers: Profile close; Keep Editing; Discard and Close.

## Connections

- [full-graph-default.png](03-connections/full-graph-default.png) — Connections full-canvas default with all family and general links visible. Covers: Graph nodes; zoom controls; expansion controls; search icon.
- [zoom-in-result.png](03-connections/zoom-in-result.png) — Connections graph after activating Zoom In. Covers: Zoom In.
- [zoom-out-result.png](03-connections/zoom-out-result.png) — Connections graph after activating Zoom Out. Covers: Zoom Out.
- [fit-view-result.png](03-connections/fit-view-result.png) — Connections graph restored with Fit View. Covers: Fit View.
- [relationship-filter-result.png](03-connections/relationship-filter-result.png) — Connections graph after toggling the General relationship type. Covers: Parents; Children; Siblings; Spouses; General.
- [search-open.png](03-connections/search-open.png) — Collapsed Connections search expanded from its icon control. Covers: Search icon; search field; close search.
- [search-results.png](03-connections/search-results.png) — Connections search results for a long bilingual synthetic person. Covers: Search result selection.
- [person-selected.png](03-connections/person-selected.png) — Selected-person inspector over the graph with a long bilingual name. Covers: Person node; View Profile; View Family Tree; Compare; Journal; Add Relationship.
- [relationship-path.png](03-connections/relationship-path.png) — Primary relationship proof path highlighted while other edges recede. Covers: Why; path selector; exit path.
- [add-relationship-dialog.png](03-connections/add-relationship-dialog.png) — Add Relationship dialog opened from the selected inspector. Covers: Add Relationship; type controls; Cancel.
- [compare-picker.png](03-connections/compare-picker.png) — Compare picker opened from the selected inspector. Covers: Compare; person choices; close.
- [compare-result.png](03-connections/compare-result.png) — Two-person relationship comparison result. Covers: Compare person; View from controls; close.
- [journal-open.png](03-connections/journal-open.png) — Selected person's Journal opened without leaving Connections. Covers: Journal; Journal toolbar; close.
- [overflow-open.png](03-connections/overflow-open.png) — Selected-person overflow menu with edit and destructive actions separated. Covers: More actions; Edit Person; Delete.
- [edit-person-dialog.png](03-connections/edit-person-dialog.png) — Edit Person dialog opened from the Connections overflow. Covers: Edit Person; Save; Cancel; close.
- [remove-person-confirmation.png](03-connections/remove-person-confirmation.png) — Remove Person confirmation reached safely on synthetic data. Covers: Delete; Cancel; confirmation.
- [person-closed.png](03-connections/person-closed.png) — Full graph restored after closing the selected-person inspector. Covers: Close selected person.

## Family Tree

- [tree-default.png](04-family-tree/tree-default.png) — Diagram-first Family Tree with focus and compact canvas controls. Covers: Family Focus search; legend; zoom; fit; center; reload.
- [legend-visible.png](04-family-tree/legend-visible.png) — Family Tree legend displayed as a compact contextual overlay. Covers: Show Legend; maternal; paternal; marriage; parent-child; sibling.
- [zoom-in-result.png](04-family-tree/zoom-in-result.png) — Family Tree after activating Zoom In. Covers: Zoom in.
- [zoom-out-result.png](04-family-tree/zoom-out-result.png) — Family Tree after activating Zoom Out. Covers: Zoom out.
- [fit-result.png](04-family-tree/fit-result.png) — Family Tree fitted to the available canvas. Covers: Fit diagram to viewport.
- [center-focus-result.png](04-family-tree/center-focus-result.png) — Family Tree centered on the current Family Focus. Covers: Center focus.
- [focus-search-results.png](04-family-tree/focus-search-results.png) — Family Focus search results for a long bilingual name. Covers: Family Focus search; result selection.
- [focus-changed.png](04-family-tree/focus-changed.png) — Family Tree reoriented around a different person. Covers: Search result; Return to My Family View.
- [person-selected.png](04-family-tree/person-selected.png) — Family Tree selected-person inspector with bilingual facts and relationship context. Covers: Make Family Focus; View Profile; View in Connections; Journal; fact actions.
- [journal-open.png](04-family-tree/journal-open.png) — Journal opened from the Family Tree inspector. Covers: Journal; close.
- [add-family-fact-dialog.png](04-family-tree/add-family-fact-dialog.png) — Add Family Fact dialog opened from the Family Tree. Covers: Add Family Fact; type controls; Cancel.
- [edit-stored-fact-dialog.png](04-family-tree/edit-stored-fact-dialog.png) — Stored family fact editor with proof and mutation controls. Covers: Edit Stored Fact; Save; Remove; Close.
- [remove-stored-fact-confirmation.png](04-family-tree/remove-stored-fact-confirmation.png) — Stored family fact removal confirmation reached safely. Covers: Remove Stored Fact; Cancel; confirmation.
- [edit-person-dialog.png](04-family-tree/edit-person-dialog.png) — Edit Person dialog opened from Family Tree context. Covers: Edit Person; Save; Cancel.
- [person-closed.png](04-family-tree/person-closed.png) — Family Tree canvas restored after closing the inspector. Covers: Close selected person.

## Search

- [mixed-results.png](05-search/mixed-results.png) — Mixed deterministic Search results with category controls and Journal content. Covers: Search; clear; suggestions; categories; result actions.
- [journal-filter.png](05-search/journal-filter.png) — Search results narrowed with the Journals category control. Covers: Journals filter; Open Journal; Details.
- [journal-result-open.png](05-search/journal-result-open.png) — Journal search result opened in context. Covers: Open Journal; close.
- [connections-filter.png](05-search/connections-filter.png) — Search category narrowed to relationship and connection results. Covers: Connections filter; result actions.
- [cleared.png](05-search/cleared.png) — Search returned to its calm initial state using Clear. Covers: Clear; suggestions; Search disabled.
- [suggestion-result.png](05-search/suggestion-result.png) — Search suggestion activated and rendered deterministic local results. Covers: Suggestion chip; result actions.

## Journal

- [view-mode.png](06-journal/view-mode.png) — Canonical Journal in calm read mode with status visible. Covers: View; Edit; Preview; Save; Cancel; Revert; Quick Append; Reload.
- [quick-append-dialog.png](06-journal/quick-append-dialog.png) — Quick Append dialog before any synthetic write. Covers: Heading; Entry; Append; Cancel.
- [edit-mode.png](06-journal/edit-mode.png) — Journal edit mode with writing actions and disabled Preview before changes. Covers: Journal Markdown; Save; Cancel; Reload.
- [dirty-tab-guard.png](06-journal/dirty-tab-guard.png) — Unsaved Journal guard when switching profile tabs. Covers: Keep Editing; Discard.
- [preview-dirty.png](06-journal/preview-dirty.png) — Dirty Journal draft rendered safely in Preview mode. Covers: View; Edit; Preview; Save; Cancel; Revert; Quick Append; Reload.

## Backups

- [backup-library.png](07-backups/backup-library.png) — Backup library with human-readable categories and data-location summary. Covers: Create Backup; Details; Open Folder; Verify; Restore; DataRoot actions.
- [create-backup-dialog.png](07-backups/create-backup-dialog.png) — Create Manual Backup dialog before any additional snapshot is written. Covers: Label; Cancel; Create Backup; close.
- [backup-details.png](07-backups/backup-details.png) — Backup details with synthetic counts and verification metadata. Covers: View Details; close.
- [verification-success.png](07-backups/verification-success.png) — Successful backup verification summary. Covers: Verify; close.
- [restore-confirmation.png](07-backups/restore-confirmation.png) — Verified synthetic backup restore confirmation before mutation. Covers: Cancel; Restore Backup.

## DataRoot

- [location-details.png](08-data-root/location-details.png) — Technical Data Root path revealed only on request. Covers: Location details; Open Folder; Validate; Change Location.
- [health-validation.png](08-data-root/health-validation.png) — Data Root health validation with human-readable status and technical checks. Covers: Validate; Refresh; close.
- [change-location-dialog.png](08-data-root/change-location-dialog.png) — Change Data Root dialog with explicit copy-versus-switch choices. Covers: Move Current Data; Switch to Existing; Cancel.

## First Run

- [welcome-default.png](09-first-run/welcome-default.png) — First-run recovery boundary with three safe setup routes. Covers: Use Existing Data Root; Restore From Backup; Create New Data Root.
- [use-existing-route.png](09-first-run/use-existing-route.png) — Use Existing Data Root route before path inspection. Covers: Path; Browse; Inspect Data Root; Back.
- [restore-route.png](09-first-run/restore-route.png) — Restore From Backup route with source and destination kept distinct. Covers: Backup source; Browse; Verify Backup; Back.
- [create-route.png](09-first-run/create-route.png) — Create New Data Root route before any filesystem mutation. Covers: Location; name; gender; Review; Back.

## Recovery

- [missing-root.png](10-recovery/missing-root.png) — Missing-root recovery state with the saved synthetic location disclosed safely. Covers: Retry; Use Existing; Restore; Create New.
- [missing-root-use-existing.png](10-recovery/missing-root-use-existing.png) — Recovery route for selecting a replacement existing Data Root. Covers: Path; Browse; Inspect; Back.
- [read-only-root.png](10-recovery/read-only-root.png) — Configured read-only state with persistent semantic warning. Covers: Read-only banner; navigation; non-mutating controls.
- [service-unavailable.png](10-recovery/service-unavailable.png) — Synthetic local-service startup failure with safe recovery actions. Covers: Retry Connection; Open Application Folder; Show Technical Details; Exit.
- [service-unavailable-details.png](10-recovery/service-unavailable-details.png) — Startup failure technical diagnostics revealed on request. Covers: Hide Details; Retry; Open Folder; Exit.

## Hermes

- [tool-selected.png](11-hermes/tool-selected.png) — Hermes deterministic tool console with safe synthetic arguments. Covers: Tool selector; catalog; Arguments; Run tool.
- [tool-result.png](11-hermes/tool-result.png) — Hermes structured output containing only isolated synthetic people. Covers: Run tool; structured output; catalog selection.

## Cross-Screen

- [responsive-980x640.png](12-cross-screen/responsive-980x640.png) — configured minimum responsive shell and full-canvas Connections layout. Covers: Sidebar; Perspective of; navigation; canvas controls.
- [responsive-1366x768.png](12-cross-screen/responsive-1366x768.png) — 1366x768 responsive shell and full-canvas Connections layout. Covers: Sidebar; Perspective of; navigation; canvas controls.
- [responsive-1440x900.png](12-cross-screen/responsive-1440x900.png) — 1440x900 responsive shell and full-canvas Connections layout. Covers: Sidebar; Perspective of; navigation; canvas controls.
- [responsive-1920x1080.png](12-cross-screen/responsive-1920x1080.png) — 1920x1080 responsive shell and full-canvas Connections layout. Covers: Sidebar; Perspective of; navigation; canvas controls.
