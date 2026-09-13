# Phase 10 Final UI Review

Every image was freshly captured from the real application with an isolated, reproducible synthetic bootstrap and Data Root. No production names, journals, backup labels, IDs, or private filesystem paths are used.

## Shell

| File | Theme | Viewport | Demonstrates | Reference status | Controls/states shown |
|---|---|---:|---|---|---|
| [perspective-dropdown.png](00-shell/perspective-dropdown.png) | light | 1500×1000 | Application-wide Perspective of control with person choices open. | Inferred | Perspective of; person options; dropdown close |

## People

| File | Theme | Viewport | Demonstrates | Reference status | Controls/states shown |
|---|---|---:|---|---|---|
| [directory-default.png](01-people/directory-default.png) | light | 1500×1000 | People directory default with filters, search, sorting, groups, and restrained row actions. | Reference-matched | Add Person; filters; search; sort; Profile; Edit; Delete |
| [row-actions-hover.png](01-people/row-actions-hover.png) | light | 1500×1000 | People row hover revealing the restrained destructive action. | Inferred | Profile; Edit; Delete |
| [remove-person-confirmation.png](01-people/remove-person-confirmation.png) | light | 1500×1000 | People row Remove confirmation on isolated synthetic data. | Inferred | Delete; Cancel; confirmation |
| [add-person-dialog.png](01-people/add-person-dialog.png) | light | 1500×1000 | Add Person dialog with human identity fields and group choices. | Reference-matched | Add Person; Save; Cancel; close |
| [family-filter-selected.png](01-people/family-filter-selected.png) | light | 1500×1000 | People directory with Family group selected. | Inferred | Family filter; All; Clear filters |
| [relationship-sort.png](01-people/relationship-sort.png) | light | 1500×1000 | People directory sorted by relationship to the current perspective. | Inferred | Sort control; Relationship option |
| [search-result.png](01-people/search-result.png) | light | 1500×1000 | People directory filtered by an Urdu alias. | Inferred | Search field; Clear filters; result Profile/Edit/Delete |

## Profile

| File | Theme | Viewport | Demonstrates | Reference status | Controls/states shown |
|---|---|---:|---|---|---|
| [profile-default.png](02-profile/profile-default.png) | light | 1500×1000 | Long-name bilingual profile in the locked information order. | Reference-matched | Relationship Path; View from; Family Tree; Edit; Compare; overflow; tabs; close |
| [connections-tab.png](02-profile/connections-tab.png) | light | 1500×1000 | Profile Connections tab with stored and derived family context. | Reference-matched | Connections tab; related-person links |
| [edit-person-dialog.png](02-profile/edit-person-dialog.png) | light | 1500×1000 | Profile Edit Person dialog over the preserved profile context. | Reference-matched | Edit Person; Save; Cancel; close |
| [compare-picker.png](02-profile/compare-picker.png) | light | 1500×1000 | Profile Compare picker with synthetic people. | Reference-matched | Compare; person choices; close |
| [compare-result.png](02-profile/compare-result.png) | light | 1500×1000 | Profile comparison result with perspective-aware labels. | Reference-matched | Compare choice; View from; close |
| [overflow-open.png](02-profile/overflow-open.png) | light | 1500×1000 | Profile overflow menu keeping Remove Person out of the everyday action row. | Inferred | More profile actions; Remove Person |
| [remove-person-confirmation.png](02-profile/remove-person-confirmation.png) | light | 1500×1000 | Profile Remove Person confirmation on isolated synthetic data. | Inferred | Remove Person; Cancel; confirmation |
| [dirty-close-guard.png](02-profile/dirty-close-guard.png) | light | 1500×1000 | Profile close guard preserving a dirty Journal draft. | Inferred | Profile close; Keep Editing; Discard and Close |

## Connections

| File | Theme | Viewport | Demonstrates | Reference status | Controls/states shown |
|---|---|---:|---|---|---|
| [full-graph-default.png](03-connections/full-graph-default.png) | light | 1500×1000 | Connections full-canvas default with all family and general links visible. | Inferred | Graph nodes; zoom controls; expansion controls; search icon |
| [fullscreen.png](03-connections/fullscreen.png) | light | 1500×1000 | Connections immersive mode keeps the graph and floating controls usable. | Inferred | Exit fullscreen; search; zoom; fit; legend |
| [zoom-in-result.png](03-connections/zoom-in-result.png) | light | 1500×1000 | Connections graph after activating Zoom In. | Inferred | Zoom In |
| [zoom-out-result.png](03-connections/zoom-out-result.png) | light | 1500×1000 | Connections graph after activating Zoom Out. | Inferred | Zoom Out |
| [fit-view-result.png](03-connections/fit-view-result.png) | light | 1500×1000 | Connections graph restored with Fit View. | Inferred | Fit View |
| [relationship-filter-result.png](03-connections/relationship-filter-result.png) | light | 1500×1000 | Connections graph after toggling the General relationship type. | Inferred | Parents; Children; Siblings; Spouses; General |
| [search-open.png](03-connections/search-open.png) | light | 1500×1000 | Collapsed Connections search expanded from its icon control. | Inferred | Search icon; search field; close search |
| [search-results.png](03-connections/search-results.png) | light | 1500×1000 | Connections search results for a long bilingual synthetic person. | Inferred | Search result selection |
| [person-selected.png](03-connections/person-selected.png) | light | 1500×1000 | Selected-person inspector over the graph with a long bilingual name. | Reference-matched | Person node; View Profile; View Family Tree; Compare; Journal; Add Relationship |
| [relationship-path.png](03-connections/relationship-path.png) | light | 1500×1000 | Primary relationship proof path highlighted while other edges recede. | Inferred | Why; path selector; exit path |
| [add-relationship-dialog.png](03-connections/add-relationship-dialog.png) | light | 1500×1000 | Add Relationship dialog opened from the selected inspector. | Reference-matched | Add Relationship; type controls; Cancel |
| [compare-picker.png](03-connections/compare-picker.png) | light | 1500×1000 | Compare picker opened from the selected inspector. | Inferred | Compare; person choices; close |
| [compare-result.png](03-connections/compare-result.png) | light | 1500×1000 | Two-person relationship comparison result. | Inferred | Compare person; View from controls; close |
| [journal-open.png](03-connections/journal-open.png) | light | 1500×1000 | Selected person's Journal opened without leaving Connections. | Inferred | Journal; Journal toolbar; close |
| [overflow-open.png](03-connections/overflow-open.png) | light | 1500×1000 | Selected-person overflow menu with edit and destructive actions separated. | Inferred | More actions; Edit Person; Delete |
| [edit-person-dialog.png](03-connections/edit-person-dialog.png) | light | 1500×1000 | Edit Person dialog opened from the Connections overflow. | Inferred | Edit Person; Save; Cancel; close |
| [remove-person-confirmation.png](03-connections/remove-person-confirmation.png) | light | 1500×1000 | Remove Person confirmation reached safely on synthetic data. | Inferred | Delete; Cancel; confirmation |
| [person-closed.png](03-connections/person-closed.png) | light | 1500×1000 | Full graph restored after closing the selected-person inspector. | Inferred | Close selected person |

## Family Tree

| File | Theme | Viewport | Demonstrates | Reference status | Controls/states shown |
|---|---|---:|---|---|---|
| [tree-default.png](04-family-tree/tree-default.png) | light | 1500×1000 | Diagram-first Family Tree with focus and compact canvas controls. | Reference-matched | Family Focus search; legend; zoom; fit; center; reload |
| [legend-visible.png](04-family-tree/legend-visible.png) | light | 1500×1000 | Family Tree legend displayed as a compact contextual overlay. | Reference-matched | Show Legend; maternal; paternal; marriage; parent-child; sibling |
| [zoom-in-result.png](04-family-tree/zoom-in-result.png) | light | 1500×1000 | Family Tree after activating Zoom In. | Inferred | Zoom in |
| [zoom-out-result.png](04-family-tree/zoom-out-result.png) | light | 1500×1000 | Family Tree after activating Zoom Out. | Inferred | Zoom out |
| [fit-result.png](04-family-tree/fit-result.png) | light | 1500×1000 | Family Tree fitted to the available canvas. | Inferred | Fit diagram to viewport |
| [center-focus-result.png](04-family-tree/center-focus-result.png) | light | 1500×1000 | Family Tree centered on the current Family Focus. | Inferred | Center focus |
| [focus-search-results.png](04-family-tree/focus-search-results.png) | light | 1500×1000 | Family Focus search results for a long bilingual name. | Inferred | Family Focus search; result selection |
| [focus-changed.png](04-family-tree/focus-changed.png) | light | 1500×1000 | Family Tree reoriented around a different person. | Inferred | Search result; Return to My Family View |
| [person-selected.png](04-family-tree/person-selected.png) | light | 1500×1000 | Family Tree selected-person inspector with bilingual facts and relationship context. | Reference-matched | Make Family Focus; View Profile; View in Connections; Journal; fact actions |
| [journal-open.png](04-family-tree/journal-open.png) | light | 1500×1000 | Journal opened from the Family Tree inspector. | Inferred | Journal; close |
| [add-family-fact-dialog.png](04-family-tree/add-family-fact-dialog.png) | light | 1500×1000 | Add Family Fact dialog opened from the Family Tree. | Inferred | Add Family Fact; type controls; Cancel |
| [edit-person-dialog.png](04-family-tree/edit-person-dialog.png) | light | 1500×1000 | Edit Person dialog opened from Family Tree context. | Inferred | Edit Person; Save; Cancel |
| [person-closed.png](04-family-tree/person-closed.png) | light | 1500×1000 | Family Tree canvas restored after closing the inspector. | Inferred | Close selected person |

## Search

| File | Theme | Viewport | Demonstrates | Reference status | Controls/states shown |
|---|---|---:|---|---|---|
| [mixed-results.png](05-search/mixed-results.png) | light | 1500×1000 | Mixed deterministic Search results with category controls and Journal content. | Inferred | Search; clear; suggestions; categories; result actions |
| [journal-filter.png](05-search/journal-filter.png) | light | 1500×1000 | Search results narrowed with the Journals category control. | Inferred | Journals filter; Open Journal; Details |
| [journal-result-open.png](05-search/journal-result-open.png) | light | 1500×1000 | Journal search result opened in context. | Inferred | Open Journal; close |
| [connections-filter.png](05-search/connections-filter.png) | light | 1500×1000 | Search category narrowed to relationship and connection results. | Inferred | Connections filter; result actions |
| [cleared.png](05-search/cleared.png) | light | 1500×1000 | Search returned to its calm initial state using Clear. | Inferred | Clear; suggestions; Search disabled |
| [suggestion-result.png](05-search/suggestion-result.png) | light | 1500×1000 | Search suggestion activated and rendered deterministic local results. | Inferred | Suggestion chip; result actions |

## Journal

| File | Theme | Viewport | Demonstrates | Reference status | Controls/states shown |
|---|---|---:|---|---|---|
| [view-mode.png](06-journal/view-mode.png) | light | 1500×1000 | Canonical Journal in calm read mode with status visible. | Inferred | View; Edit; Preview; Save; Cancel; Revert; Quick Append; Reload |
| [quick-append-dialog.png](06-journal/quick-append-dialog.png) | light | 1500×1000 | Quick Append dialog before any synthetic write. | Inferred | Heading; Entry; Append; Cancel |
| [edit-mode.png](06-journal/edit-mode.png) | light | 1500×1000 | Journal edit mode with writing actions and disabled Preview before changes. | Reference-matched | Journal Markdown; Save; Cancel; Reload |
| [dirty-tab-guard.png](06-journal/dirty-tab-guard.png) | light | 1500×1000 | Unsaved Journal guard when switching profile tabs. | Inferred | Keep Editing; Discard |
| [preview-dirty.png](06-journal/preview-dirty.png) | light | 1500×1000 | Dirty Journal draft rendered safely in Preview mode. | Inferred | View; Edit; Preview; Save; Cancel; Revert; Quick Append; Reload |

## Backups

| File | Theme | Viewport | Demonstrates | Reference status | Controls/states shown |
|---|---|---:|---|---|---|
| [backup-library.png](07-backups/backup-library.png) | light | 1500×1000 | Backup library with human-readable categories and data-location summary. | Inferred | Create Backup; Details; Open Folder; Verify; Restore; DataRoot actions |
| [create-backup-dialog.png](07-backups/create-backup-dialog.png) | light | 1500×1000 | Create Manual Backup dialog before any additional snapshot is written. | Reference-matched | Label; Cancel; Create Backup; close |
| [backup-details.png](07-backups/backup-details.png) | light | 1500×1000 | Backup details with synthetic counts and verification metadata. | Reference-matched | View Details; close |
| [verification-success.png](07-backups/verification-success.png) | light | 1500×1000 | Successful backup verification summary. | Reference-matched | Verify; close |
| [restore-confirmation.png](07-backups/restore-confirmation.png) | light | 1500×1000 | Verified synthetic backup restore confirmation before mutation. | Reference-matched | Cancel; Restore Backup |

## DataRoot

| File | Theme | Viewport | Demonstrates | Reference status | Controls/states shown |
|---|---|---:|---|---|---|
| [location-details.png](08-data-root/location-details.png) | light | 1500×1000 | Technical Data Root path revealed only on request. | Inferred | Location details; Open Folder; Validate; Change Location |
| [health-validation.png](08-data-root/health-validation.png) | light | 1500×1000 | Data Root health validation with human-readable status and technical checks. | Reference-matched | Validate; Refresh; close |
| [change-location-dialog.png](08-data-root/change-location-dialog.png) | light | 1500×1000 | Change Data Root dialog with explicit copy-versus-switch choices. | Reference-matched | Move Current Data; Switch to Existing; Cancel |

## First Run

| File | Theme | Viewport | Demonstrates | Reference status | Controls/states shown |
|---|---|---:|---|---|---|
| [welcome-default.png](09-first-run/welcome-default.png) | light | 1500×1000 | First-run recovery boundary with three safe setup routes. | Reference-matched | Use Existing Data Root; Restore From Backup; Create New Data Root |
| [use-existing-route.png](09-first-run/use-existing-route.png) | light | 1500×1000 | Use Existing Data Root route before path inspection. | Reference-matched | Path; Browse; Inspect Data Root; Back |
| [restore-route.png](09-first-run/restore-route.png) | light | 1500×1000 | Restore From Backup route with source and destination kept distinct. | Reference-matched | Backup source; Browse; Verify Backup; Back |
| [create-route.png](09-first-run/create-route.png) | light | 1500×1000 | Create New Data Root route before any filesystem mutation. | Reference-matched | Location; name; gender; Review; Back |

## Recovery

| File | Theme | Viewport | Demonstrates | Reference status | Controls/states shown |
|---|---|---:|---|---|---|
| [missing-root.png](10-recovery/missing-root.png) | light | 1500×1000 | Missing-root recovery state with the saved synthetic location disclosed safely. | Reference-matched | Retry; Use Existing; Restore; Create New |
| [missing-root-use-existing.png](10-recovery/missing-root-use-existing.png) | light | 1500×1000 | Recovery route for selecting a replacement existing Data Root. | Reference-matched | Path; Browse; Inspect; Back |
| [read-only-root.png](10-recovery/read-only-root.png) | light | 1500×1000 | Configured read-only state with persistent semantic warning. | Inferred | Read-only banner; navigation; non-mutating controls |
| [service-unavailable.png](10-recovery/service-unavailable.png) | light | 1500×1000 | Synthetic local-service startup failure with safe recovery actions. | Reference-matched | Retry Connection; Open Application Folder; Show Technical Details; Exit |
| [service-unavailable-details.png](10-recovery/service-unavailable-details.png) | light | 1500×1000 | Startup failure technical diagnostics revealed on request. | Reference-matched | Hide Details; Retry; Open Folder; Exit |

## Errors

| File | Theme | Viewport | Demonstrates | Reference status | Controls/states shown |
|---|---|---:|---|---|---|
| [invalid-mutation.png](11-errors/invalid-mutation.png) | light | 1500×1000 | Canonical engine blocks a synthetic ancestry cycle and reports the validation reason. | Reference-matched | Preview Consequences; Cancel; validation message |
| [light-10-recovery-read-only-root.png](11-errors/light-10-recovery-read-only-root.png) | light | 1500×1000 | Error, warning, or constrained-state evidence from the same live application state. Source state: 10-recovery/read-only-root.png. | Inferred | Read-only banner; navigation; non-mutating controls |
| [light-10-recovery-service-unavailable.png](11-errors/light-10-recovery-service-unavailable.png) | light | 1500×1000 | Error, warning, or constrained-state evidence from the same live application state. Source state: 10-recovery/service-unavailable.png. | Reference-matched | Retry Connection; Open Application Folder; Show Technical Details; Exit |
| [light-10-recovery-service-unavailable-details.png](11-errors/light-10-recovery-service-unavailable-details.png) | light | 1500×1000 | Error, warning, or constrained-state evidence from the same live application state. Source state: 10-recovery/service-unavailable-details.png. | Reference-matched | Hide Details; Retry; Open Folder; Exit |
| [dark-15-dark-mode-read-only.png](11-errors/dark-15-dark-mode-read-only.png) | dark | 1500×1000 | Error, warning, or constrained-state evidence from the same live application state. Source state: 15-dark-mode/read-only.png. | Inferred | Read-only banner; navigation |
| [dark-15-dark-mode-startup-failure.png](11-errors/dark-15-dark-mode-startup-failure.png) | dark | 1500×1000 | Error, warning, or constrained-state evidence from the same live application state. Source state: 15-dark-mode/startup-failure.png. | Inferred | Retry Connection; details; Exit |

## Dialogs

| File | Theme | Viewport | Demonstrates | Reference status | Controls/states shown |
|---|---|---:|---|---|---|
| [light-03-connections-add-relationship-dialog.png](12-dialogs/light-03-connections-add-relationship-dialog.png) | light | 1500×1000 | Cross-screen dialog evidence from the same live application state. Source state: 03-connections/add-relationship-dialog.png. | Reference-matched | Add Relationship; type controls; Cancel |
| [dark-15-dark-mode-add-relationship-dialog.png](12-dialogs/dark-15-dark-mode-add-relationship-dialog.png) | dark | 1500×1000 | Cross-screen dialog evidence from the same live application state. Source state: 15-dark-mode/add-relationship-dialog.png. | Inferred | Theme switch; active dialog; Cancel |
| [light-03-connections-compare-picker.png](12-dialogs/light-03-connections-compare-picker.png) | light | 1500×1000 | Cross-screen dialog evidence from the same live application state. Source state: 03-connections/compare-picker.png. | Inferred | Compare; person choices; close |
| [light-03-connections-edit-person-dialog.png](12-dialogs/light-03-connections-edit-person-dialog.png) | light | 1500×1000 | Cross-screen dialog evidence from the same live application state. Source state: 03-connections/edit-person-dialog.png. | Inferred | Edit Person; Save; Cancel; close |
| [light-03-connections-remove-person-confirmation.png](12-dialogs/light-03-connections-remove-person-confirmation.png) | light | 1500×1000 | Cross-screen dialog evidence from the same live application state. Source state: 03-connections/remove-person-confirmation.png. | Inferred | Delete; Cancel; confirmation |
| [light-01-people-remove-person-confirmation.png](12-dialogs/light-01-people-remove-person-confirmation.png) | light | 1500×1000 | Cross-screen dialog evidence from the same live application state. Source state: 01-people/remove-person-confirmation.png. | Inferred | Delete; Cancel; confirmation |
| [light-01-people-add-person-dialog.png](12-dialogs/light-01-people-add-person-dialog.png) | light | 1500×1000 | Cross-screen dialog evidence from the same live application state. Source state: 01-people/add-person-dialog.png. | Reference-matched | Add Person; Save; Cancel; close |
| [light-02-profile-edit-person-dialog.png](12-dialogs/light-02-profile-edit-person-dialog.png) | light | 1500×1000 | Cross-screen dialog evidence from the same live application state. Source state: 02-profile/edit-person-dialog.png. | Reference-matched | Edit Person; Save; Cancel; close |
| [light-02-profile-compare-picker.png](12-dialogs/light-02-profile-compare-picker.png) | light | 1500×1000 | Cross-screen dialog evidence from the same live application state. Source state: 02-profile/compare-picker.png. | Reference-matched | Compare; person choices; close |
| [light-02-profile-remove-person-confirmation.png](12-dialogs/light-02-profile-remove-person-confirmation.png) | light | 1500×1000 | Cross-screen dialog evidence from the same live application state. Source state: 02-profile/remove-person-confirmation.png. | Inferred | Remove Person; Cancel; confirmation |
| [light-06-journal-quick-append-dialog.png](12-dialogs/light-06-journal-quick-append-dialog.png) | light | 1500×1000 | Cross-screen dialog evidence from the same live application state. Source state: 06-journal/quick-append-dialog.png. | Inferred | Heading; Entry; Append; Cancel |
| [light-06-journal-dirty-tab-guard.png](12-dialogs/light-06-journal-dirty-tab-guard.png) | light | 1500×1000 | Cross-screen dialog evidence from the same live application state. Source state: 06-journal/dirty-tab-guard.png. | Inferred | Keep Editing; Discard |
| [light-02-profile-dirty-close-guard.png](12-dialogs/light-02-profile-dirty-close-guard.png) | light | 1500×1000 | Cross-screen dialog evidence from the same live application state. Source state: 02-profile/dirty-close-guard.png. | Inferred | Profile close; Keep Editing; Discard and Close |
| [light-04-family-tree-add-family-fact-dialog.png](12-dialogs/light-04-family-tree-add-family-fact-dialog.png) | light | 1500×1000 | Cross-screen dialog evidence from the same live application state. Source state: 04-family-tree/add-family-fact-dialog.png. | Inferred | Add Family Fact; type controls; Cancel |
| [light-04-family-tree-edit-person-dialog.png](12-dialogs/light-04-family-tree-edit-person-dialog.png) | light | 1500×1000 | Cross-screen dialog evidence from the same live application state. Source state: 04-family-tree/edit-person-dialog.png. | Inferred | Edit Person; Save; Cancel |
| [light-07-backups-create-backup-dialog.png](12-dialogs/light-07-backups-create-backup-dialog.png) | light | 1500×1000 | Cross-screen dialog evidence from the same live application state. Source state: 07-backups/create-backup-dialog.png. | Reference-matched | Label; Cancel; Create Backup; close |
| [light-07-backups-restore-confirmation.png](12-dialogs/light-07-backups-restore-confirmation.png) | light | 1500×1000 | Cross-screen dialog evidence from the same live application state. Source state: 07-backups/restore-confirmation.png. | Reference-matched | Cancel; Restore Backup |
| [light-08-data-root-change-location-dialog.png](12-dialogs/light-08-data-root-change-location-dialog.png) | light | 1500×1000 | Cross-screen dialog evidence from the same live application state. Source state: 08-data-root/change-location-dialog.png. | Reference-matched | Move Current Data; Switch to Existing; Cancel |
| [dark-15-dark-mode-backup-restore-confirmation.png](12-dialogs/dark-15-dark-mode-backup-restore-confirmation.png) | dark | 1500×1000 | Cross-screen dialog evidence from the same live application state. Source state: 15-dark-mode/backup-restore-confirmation.png. | Inferred | Restore Backup; Cancel |

## Hermes

| File | Theme | Viewport | Demonstrates | Reference status | Controls/states shown |
|---|---|---:|---|---|---|
| [tool-selected.png](13-hermes/tool-selected.png) | light | 1500×1000 | Hermes deterministic tool console with safe synthetic arguments. | Inferred | Tool selector; catalog; Arguments; Run tool |
| [tool-result.png](13-hermes/tool-result.png) | light | 1500×1000 | Hermes structured output containing only isolated synthetic people. | Inferred | Run tool; structured output; catalog selection |

## Cross-Screen

| File | Theme | Viewport | Demonstrates | Reference status | Controls/states shown |
|---|---|---:|---|---|---|
| [responsive-980x640.png](14-cross-screen/responsive-980x640.png) | light | 980×640 | configured minimum responsive shell and full-canvas Connections layout. | Inferred | Sidebar; Perspective of; navigation; canvas controls |
| [responsive-1366x768.png](14-cross-screen/responsive-1366x768.png) | light | 1366×768 | 1366x768 responsive shell and full-canvas Connections layout. | Inferred | Sidebar; Perspective of; navigation; canvas controls |
| [responsive-1440x900.png](14-cross-screen/responsive-1440x900.png) | light | 1440×900 | 1440x900 responsive shell and full-canvas Connections layout. | Inferred | Sidebar; Perspective of; navigation; canvas controls |
| [responsive-1500x1000.png](14-cross-screen/responsive-1500x1000.png) | light | 1500×1000 | 1500x1000 responsive shell and full-canvas Connections layout. | Inferred | Sidebar; Perspective of; navigation; canvas controls |
| [responsive-1920x1080.png](14-cross-screen/responsive-1920x1080.png) | light | 1920×1080 | 1920x1080 responsive shell and full-canvas Connections layout. | Inferred | Sidebar; Perspective of; navigation; canvas controls |

## Dark Mode

| File | Theme | Viewport | Demonstrates | Reference status | Controls/states shown |
|---|---|---:|---|---|---|
| [first-run.png](15-dark-mode/first-run.png) | dark | 1500×1000 | First-run onboarding rendered with the persisted Dark theme before any DataRoot exists. | Inferred | Use Existing Data Root; Restore From Backup; Create New Data Root |
| [connections-default.png](15-dark-mode/connections-default.png) | dark | 1500×1000 | Real Dark mode applied live to the full Connections canvas. | Inferred | Theme switch; graph canvas; graph edges; floating controls |
| [add-relationship-dialog.png](15-dark-mode/add-relationship-dialog.png) | dark | 1500×1000 | Open relationship dialog updated live after switching to Dark mode. | Inferred | Theme switch; active dialog; Cancel |
| [shell.png](15-dark-mode/shell.png) | dark | 1500×1000 | Dark application shell with global perspective and theme controls. | Inferred | Navigation; Perspective of; theme switch |
| [people.png](15-dark-mode/people.png) | dark | 1500×1000 | Dense 52-person directory in Dark mode with bilingual and long names. | Inferred | Filters; search; sort; Add Person; row actions |
| [profile-overview.png](15-dark-mode/profile-overview.png) | dark | 1500×1000 | Synthetic long-name profile Overview in Dark mode. | Inferred | Relationship Path; Family Tree; Edit; Compare; tabs |
| [profile-connections.png](15-dark-mode/profile-connections.png) | dark | 1500×1000 | Profile Connections tab in Dark mode. | Inferred | Overview; Connections; Journal; related-person actions |
| [journal-view.png](15-dark-mode/journal-view.png) | dark | 1500×1000 | Mixed-language Journal read view in Dark mode. | Inferred | View; Edit; Preview; Quick Append; Reload |
| [journal-edit.png](15-dark-mode/journal-edit.png) | dark | 1500×1000 | Journal editor and toolbar in Dark mode. | Inferred | Editor; Save; Cancel; Preview; Revert |
| [connections-canvas.png](15-dark-mode/connections-canvas.png) | dark | 1500×1000 | Full Connections canvas in Dark mode with mixed family and general edges. | Inferred | Search; filters; zoom; fit; fullscreen |
| [connections-search.png](15-dark-mode/connections-search.png) | dark | 1500×1000 | Expanded Connections search in Dark mode. | Inferred | Search input; close search |
| [connections-selected.png](15-dark-mode/connections-selected.png) | dark | 1500×1000 | Selected-person inspector floating over the Dark graph. | Inferred | Inspector; Why; Profile; Family Tree; Compare; Journal |
| [connections-fullscreen.png](15-dark-mode/connections-fullscreen.png) | dark | 1500×1000 | Dark immersive Connections canvas with selection and controls intact. | Inferred | Exit fullscreen; inspector; graph controls |
| [family-tree.png](15-dark-mode/family-tree.png) | dark | 1500×1000 | Five-generation multipath Family Tree in Dark mode. | Inferred | Family Focus; zoom; fit; center; legend |
| [family-tree-legend.png](15-dark-mode/family-tree-legend.png) | dark | 1500×1000 | Family Tree legend in Dark mode with semantic branch colors. | Inferred | Legend; maternal; paternal; marriage; sibling |
| [family-tree-selected.png](15-dark-mode/family-tree-selected.png) | dark | 1500×1000 | Dark Family Tree selected-person inspector. | Inferred | Make Family Focus; Profile; Connections; Journal; fact actions |
| [search.png](15-dark-mode/search.png) | dark | 1500×1000 | Mixed local Search results in Dark mode. | Inferred | Search; clear; category filters; results |
| [backups.png](15-dark-mode/backups.png) | dark | 1500×1000 | Synthetic backup library in Dark mode. | Inferred | Create Backup; Details; Verify; Restore; DataRoot controls |
| [backup-create.png](15-dark-mode/backup-create.png) | dark | 1500×1000 | Create Backup dialog in Dark mode. | Inferred | Label; Create Backup; Cancel |
| [backup-restore-confirmation.png](15-dark-mode/backup-restore-confirmation.png) | dark | 1500×1000 | Backup restore confirmation in Dark mode before mutation. | Inferred | Restore Backup; Cancel |
| [data-root.png](15-dark-mode/data-root.png) | dark | 1500×1000 | Synthetic DataRoot location and health actions in Dark mode. | Inferred | Location details; Validate; Change Location |
| [data-root-health.png](15-dark-mode/data-root-health.png) | dark | 1500×1000 | DataRoot health audit in Dark mode. | Inferred | Refresh; close |
| [hermes.png](15-dark-mode/hermes.png) | dark | 1500×1000 | Hermes placeholder/tool console aligned with Dark mode. | Inferred | Tool selector; Arguments; Run tool |
| [missing-root.png](15-dark-mode/missing-root.png) | dark | 1500×1000 | Missing-root recovery in Dark mode with a synthetic location. | Inferred | Retry; Use Existing; Restore; Create New |
| [read-only.png](15-dark-mode/read-only.png) | dark | 1500×1000 | Read-only DataRoot warning remains legible in Dark mode. | Inferred | Read-only banner; navigation |
| [startup-failure.png](15-dark-mode/startup-failure.png) | dark | 1500×1000 | Synthetic startup failure recovery in Dark mode. | Inferred | Retry Connection; details; Exit |

## Reference Comparisons

| File | Theme | Viewport | Demonstrates | Reference status | Controls/states shown |
|---|---|---:|---|---|---|
| [light-09-first-run-welcome-default.png](16-reference-comparisons/light-09-first-run-welcome-default.png) | light | 1500×1000 | Final implementation corresponding to the supplied reference; dynamic fixture data intentionally differs. Source state: 09-first-run/welcome-default.png. | Reference-matched | Use Existing Data Root; Restore From Backup; Create New Data Root |
| [light-09-first-run-use-existing-route.png](16-reference-comparisons/light-09-first-run-use-existing-route.png) | light | 1500×1000 | Final implementation corresponding to the supplied reference; dynamic fixture data intentionally differs. Source state: 09-first-run/use-existing-route.png. | Reference-matched | Path; Browse; Inspect Data Root; Back |
| [light-09-first-run-restore-route.png](16-reference-comparisons/light-09-first-run-restore-route.png) | light | 1500×1000 | Final implementation corresponding to the supplied reference; dynamic fixture data intentionally differs. Source state: 09-first-run/restore-route.png. | Reference-matched | Backup source; Browse; Verify Backup; Back |
| [light-09-first-run-create-route.png](16-reference-comparisons/light-09-first-run-create-route.png) | light | 1500×1000 | Final implementation corresponding to the supplied reference; dynamic fixture data intentionally differs. Source state: 09-first-run/create-route.png. | Reference-matched | Location; name; gender; Review; Back |
| [light-03-connections-person-selected.png](16-reference-comparisons/light-03-connections-person-selected.png) | light | 1500×1000 | Final implementation corresponding to the supplied reference; dynamic fixture data intentionally differs. Source state: 03-connections/person-selected.png. | Reference-matched | Person node; View Profile; View Family Tree; Compare; Journal; Add Relationship |
| [light-03-connections-add-relationship-dialog.png](16-reference-comparisons/light-03-connections-add-relationship-dialog.png) | light | 1500×1000 | Final implementation corresponding to the supplied reference; dynamic fixture data intentionally differs. Source state: 03-connections/add-relationship-dialog.png. | Reference-matched | Add Relationship; type controls; Cancel |
| [light-11-errors-invalid-mutation.png](16-reference-comparisons/light-11-errors-invalid-mutation.png) | light | 1500×1000 | Final implementation corresponding to the supplied reference; dynamic fixture data intentionally differs. Source state: 11-errors/invalid-mutation.png. | Reference-matched | Preview Consequences; Cancel; validation message |
| [light-01-people-directory-default.png](16-reference-comparisons/light-01-people-directory-default.png) | light | 1500×1000 | Final implementation corresponding to the supplied reference; dynamic fixture data intentionally differs. Source state: 01-people/directory-default.png. | Reference-matched | Add Person; filters; search; sort; Profile; Edit; Delete |
| [light-01-people-add-person-dialog.png](16-reference-comparisons/light-01-people-add-person-dialog.png) | light | 1500×1000 | Final implementation corresponding to the supplied reference; dynamic fixture data intentionally differs. Source state: 01-people/add-person-dialog.png. | Reference-matched | Add Person; Save; Cancel; close |
| [light-02-profile-profile-default.png](16-reference-comparisons/light-02-profile-profile-default.png) | light | 1500×1000 | Final implementation corresponding to the supplied reference; dynamic fixture data intentionally differs. Source state: 02-profile/profile-default.png. | Reference-matched | Relationship Path; View from; Family Tree; Edit; Compare; overflow; tabs; close |
| [light-02-profile-connections-tab.png](16-reference-comparisons/light-02-profile-connections-tab.png) | light | 1500×1000 | Final implementation corresponding to the supplied reference; dynamic fixture data intentionally differs. Source state: 02-profile/connections-tab.png. | Reference-matched | Connections tab; related-person links |
| [light-02-profile-edit-person-dialog.png](16-reference-comparisons/light-02-profile-edit-person-dialog.png) | light | 1500×1000 | Final implementation corresponding to the supplied reference; dynamic fixture data intentionally differs. Source state: 02-profile/edit-person-dialog.png. | Reference-matched | Edit Person; Save; Cancel; close |
| [light-02-profile-compare-picker.png](16-reference-comparisons/light-02-profile-compare-picker.png) | light | 1500×1000 | Final implementation corresponding to the supplied reference; dynamic fixture data intentionally differs. Source state: 02-profile/compare-picker.png. | Reference-matched | Compare; person choices; close |
| [light-02-profile-compare-result.png](16-reference-comparisons/light-02-profile-compare-result.png) | light | 1500×1000 | Final implementation corresponding to the supplied reference; dynamic fixture data intentionally differs. Source state: 02-profile/compare-result.png. | Reference-matched | Compare choice; View from; close |
| [light-06-journal-edit-mode.png](16-reference-comparisons/light-06-journal-edit-mode.png) | light | 1500×1000 | Final implementation corresponding to the supplied reference; dynamic fixture data intentionally differs. Source state: 06-journal/edit-mode.png. | Reference-matched | Journal Markdown; Save; Cancel; Reload |
| [light-04-family-tree-tree-default.png](16-reference-comparisons/light-04-family-tree-tree-default.png) | light | 1500×1000 | Final implementation corresponding to the supplied reference; dynamic fixture data intentionally differs. Source state: 04-family-tree/tree-default.png. | Reference-matched | Family Focus search; legend; zoom; fit; center; reload |
| [light-04-family-tree-legend-visible.png](16-reference-comparisons/light-04-family-tree-legend-visible.png) | light | 1500×1000 | Final implementation corresponding to the supplied reference; dynamic fixture data intentionally differs. Source state: 04-family-tree/legend-visible.png. | Reference-matched | Show Legend; maternal; paternal; marriage; parent-child; sibling |
| [light-04-family-tree-person-selected.png](16-reference-comparisons/light-04-family-tree-person-selected.png) | light | 1500×1000 | Final implementation corresponding to the supplied reference; dynamic fixture data intentionally differs. Source state: 04-family-tree/person-selected.png. | Reference-matched | Make Family Focus; View Profile; View in Connections; Journal; fact actions |
| [light-07-backups-create-backup-dialog.png](16-reference-comparisons/light-07-backups-create-backup-dialog.png) | light | 1500×1000 | Final implementation corresponding to the supplied reference; dynamic fixture data intentionally differs. Source state: 07-backups/create-backup-dialog.png. | Reference-matched | Label; Cancel; Create Backup; close |
| [light-07-backups-backup-details.png](16-reference-comparisons/light-07-backups-backup-details.png) | light | 1500×1000 | Final implementation corresponding to the supplied reference; dynamic fixture data intentionally differs. Source state: 07-backups/backup-details.png. | Reference-matched | View Details; close |
| [light-07-backups-verification-success.png](16-reference-comparisons/light-07-backups-verification-success.png) | light | 1500×1000 | Final implementation corresponding to the supplied reference; dynamic fixture data intentionally differs. Source state: 07-backups/verification-success.png. | Reference-matched | Verify; close |
| [light-07-backups-restore-confirmation.png](16-reference-comparisons/light-07-backups-restore-confirmation.png) | light | 1500×1000 | Final implementation corresponding to the supplied reference; dynamic fixture data intentionally differs. Source state: 07-backups/restore-confirmation.png. | Reference-matched | Cancel; Restore Backup |
| [light-08-data-root-health-validation.png](16-reference-comparisons/light-08-data-root-health-validation.png) | light | 1500×1000 | Final implementation corresponding to the supplied reference; dynamic fixture data intentionally differs. Source state: 08-data-root/health-validation.png. | Reference-matched | Validate; Refresh; close |
| [light-08-data-root-change-location-dialog.png](16-reference-comparisons/light-08-data-root-change-location-dialog.png) | light | 1500×1000 | Final implementation corresponding to the supplied reference; dynamic fixture data intentionally differs. Source state: 08-data-root/change-location-dialog.png. | Reference-matched | Move Current Data; Switch to Existing; Cancel |
| [light-10-recovery-missing-root.png](16-reference-comparisons/light-10-recovery-missing-root.png) | light | 1500×1000 | Final implementation corresponding to the supplied reference; dynamic fixture data intentionally differs. Source state: 10-recovery/missing-root.png. | Reference-matched | Retry; Use Existing; Restore; Create New |
| [light-10-recovery-missing-root-use-existing.png](16-reference-comparisons/light-10-recovery-missing-root-use-existing.png) | light | 1500×1000 | Final implementation corresponding to the supplied reference; dynamic fixture data intentionally differs. Source state: 10-recovery/missing-root-use-existing.png. | Reference-matched | Path; Browse; Inspect; Back |
| [light-10-recovery-service-unavailable.png](16-reference-comparisons/light-10-recovery-service-unavailable.png) | light | 1500×1000 | Final implementation corresponding to the supplied reference; dynamic fixture data intentionally differs. Source state: 10-recovery/service-unavailable.png. | Reference-matched | Retry Connection; Open Application Folder; Show Technical Details; Exit |
| [light-10-recovery-service-unavailable-details.png](16-reference-comparisons/light-10-recovery-service-unavailable-details.png) | light | 1500×1000 | Final implementation corresponding to the supplied reference; dynamic fixture data intentionally differs. Source state: 10-recovery/service-unavailable-details.png. | Reference-matched | Hide Details; Retry; Open Folder; Exit |
