# Phase 6 — Search Verification

## Baseline and final-SHA convention

- Starting branch: `main`.
- `PHASE6_START_SHA`: `b2bda47bf00b8306dd51223a92ac9d7c354849b8`.
- The starting SHA was both local `HEAD` and `origin/main`, and is the frozen Phase 5 final SHA.
- Production database baseline SHA-256: `3258C738F9D65B23B15970D0E1E7389E8584A35BA8E26030249061BAF74E096E`.
- Production Journal baseline: 35 canonical `journal.md` files, recorded by path, bytes, and SHA-256 before Search work.
- Final-SHA convention: the Phase 6 commit containing this report is `PHASE6_FINAL_SHA`. Its exact self-referential value and exact-SHA CI run are recorded in the final handoff because a commit cannot embed its own hash.

## Audited architecture and authoritative sources

The existing Search service, endpoint, view, application navigation, People group filtering, Relationships handoff, family path engine, shared Journal modal, types, API client, and CSS were audited and retained as the implementation seam. The confirmed gaps were default-focus family semantics, weak general/group navigation, missing alias explanations and stable React identity, shallow ranking, collapsed family paths, literal/Unicode safety, and request races.

Search remains a deterministic local composition layer:

- People and aliases: canonical SQLite rows.
- Groups and membership: canonical SQLite rows.
- General relationships: stored SQLite facts, including both endpoints, directionality, direction source, both labels, notes, and row ID.
- Family relationships: the canonical Python relationship/path engine for the explicitly supplied current perspective.
- Journals: direct canonical Markdown reads through `journals.journal_summaries()`.

No AI, Hermes, network service, embedding, fuzzy engine, search cache, search database, Journal prose column, schema migration, or frontend kinship derivation was added. `APP_SCHEMA_VERSION` remains 2.

## Query normalization and literal safety

One backend helper applies Unicode NFKC normalization, `casefold()`, and outer-whitespace trimming for comparison while preserving the original query in the response for display. Stored text is never modified. Candidate strings are compared in Python rather than relying on SQLite `LIKE`, so `%` and `_` remain literal characters and Unicode case behavior is predictable. All SQL is static or parameterized.

Coverage includes apostrophes, double quotes, angle brackets, backslashes, brackets, `%`, `_`, emoji, Urdu, mixed Urdu/Latin text, combining characters, and full-width Unicode. Search does not transliterate, stem, or fuzzy-match.

## Deterministic ranking and stable identities

People use six explicit tiers: exact canonical name, exact alias, canonical prefix, alias prefix, canonical substring, alias substring. A person appears once using its best match, and a matched alias is returned and displayed.

Relationship and group strings use exact, prefix, then substring tiers. Equal-quality results use a stable type/title/result-ID order; Journal prose follows structured matches. Repeated searches against unchanged data return identical order. API limits are validated from 1 through 100; invalid zero, negative, or over-100 values return validation errors.

Stable IDs are structural:

- `person:<person_id>`
- `group:<group_id>`
- `general:<relationship_id>`
- `family:<perspective_id>:<target_id>:<path_id>`
- `journal:<person_id>`

React keys use `result_id`, never an array index or random value.

## Categories and navigation

The four canonical categories remain `PERSON`, `RELATIONSHIP`, `GROUP`, and `JOURNAL`. The UI provides keyboard-usable All, People, Relationships, Groups, and Journals filters with counts and exposed selected state.

- Person results provide Details, View in Relationships, and Journal. Details and ordinary Relationships handoff do not change perspective.
- Group results reuse PeopleView's canonical group filter. The resulting member rows retain the existing Profile, Relationships, and Journal actions; no second people browser or pseudo-person is created.
- Journal results provide Open Journal and Details through the shared frozen Journal experience.

## Perspective-aware family and multipath behavior

The frontend supplies the current Relationships perspective to every search request. The backend validates it and derives family labels from that perspective, not metadata focus. Changing perspective reruns the last submitted query and replaces all old-perspective results without Search itself changing perspective.

English and Urdu labels come from the canonical relationship engine. Every matching canonical `path_id` gets a distinct stable family result, so simultaneous maternal/paternal or other multipath truths are preserved rather than deduplicated by display label. Family handoff deliberately establishes the result's recorded perspective and exact target before opening Relationships.

## General relationship orientation

General results expose the stored row ID, both endpoint IDs/names, symmetric or directional semantics, canonical `direction_from`, both labels, notes, and matched fields. Symmetric titles use `↔`; directional titles follow `direction_from` and use `→`.

Navigation is metadata-driven. A match only in the reverse label makes B→A the primary action; a forward-label match makes A→B primary; type/note matches use the canonical direction source. Both directions remain explicit for directional rows, and the awaited application handoff prevents perspective/target races.

## Canonical Journal search

Journal prose is scanned directly from the 35 canonical Markdown files in deterministic person order. Missing, unreadable, or invalid-UTF-8 files are skipped without creation or global failure. Snippets compact line breaks, retain Unicode, center deterministic context around the first match, and add ellipses when trimmed. React renders result text as text nodes; no `dangerouslySetInnerHTML` path exists.

Search reads never create or change Journal files. A large synthetic Journal tail match remained responsive, and its bytes stayed unchanged. A unique Journal-only marker was absent from SQLite after search.

## UI states, races, and accessibility

Search has labelled `role="search"` input semantics with autofocus, accessible button actions, keyboard-operable filters, visible selected states, an `aria-live` result list, `aria-busy`, and a loading status. Initial, Searching, no-results, and backend-error states are distinct.

The explicit-submit flow uses both `AbortController` and a monotonically increasing request sequence. A delayed older response cannot replace a newer response. Clear aborts/invalidates outstanding work, empties results, resets filters, and restores the initial state.

Hostile script, event-handler, quote, and angle-bracket text remained inert while still visible as result text. Urdu text remained readable.

## Focused verification

- Backend Search: `Codebase/Tests/Backend/test_search_phase6.py` — 57/57 passed.
- Dedicated browser Search: `npm run test:search` / `Codebase/Tests/UI/search_e2e.mjs` — 42/42 passed against a copied temporary DataRoot with hardened Edge launch arguments.
- Performance fixtures covered approximately 100 added people and a hundreds-of-KB Journal; exact, deterministic results completed within the test's interactive bound without FTS or an index database.
- Read-only coverage: backend Search succeeded while the DataRoot reported read-only; browser Search succeeded with the sandbox database and canonical Journal source files marked read-only.

## Frozen regression results

- Full backend: 379/379 passed, greater than the frozen Phase 5 total of 322.
- Legacy family audit: passed with 35 people, 44 parent-child facts, 12 marriages, 10 sibling groups, and 21 focus-person cousin paths.
- Frontend typecheck: passed.
- Frontend production build: passed; the existing non-fatal Vite dynamic/static import warning remains.
- People E2E: 18/18 passed.
- Relationships E2E: 37/37 passed.
- Family E2E: 65/65 passed.
- Journals E2E: 48/48 passed.
- Search E2E: 42/42 passed.
- Legacy isolated smoke: 18/18 assertions passed on a clean freshly started stack.
- Canonical Tauri `cargo check`: passed.

## Production integrity and visual verification

After all tests, the production database SHA-256 remained exactly `3258C738F9D65B23B15970D0E1E7389E8584A35BA8E26030249061BAF74E096E`. All 35 production Journal paths, byte lengths, and SHA-256 values matched the stored baseline through each isolated E2E safety gate. `git diff -- Database` and `git status Database/` were clean. No SQLite sidecar, Journal temporary file, search index, or cache database remained.

Only the four authorized Search screenshots are part of Phase 6:

- `Documentation/UI-Screenshots/search-people.png`
- `Documentation/UI-Screenshots/search-relationship.png`
- `Documentation/UI-Screenshots/search-journal.png`
- `Documentation/UI-Screenshots/search-group.png`

All four were inspected at full resolution. They show clear result hierarchy, distinct category tags, readable snippets and Urdu, unclipped long directional labels and buttons, balanced desktop spacing, and no giant unused content container or overlapping controls.

## Native CI and artifacts

After push, the `Build & Package Matrix` run for exact `PHASE6_FINAL_SHA` must finish terminal green for Windows x64, macOS ARM64, macOS Intel x64, and Linux x64. The four corresponding release artifacts must be present and unexpired. Run ID, exact SHA, job results, and artifact sizes are external post-commit evidence and therefore are recorded in the final handoff.

## Genuine limitations

- Search is explicit-submit rather than debounced live search; race protection still covers overlapping submissions.
- Query and category filter are component-session state and reset after navigating away and back. No persistent Search history is stored.
- Journal results are one deterministic result per canonical person, with the first match providing the snippet; Search does not enumerate every occurrence within one Journal.
- Search intentionally has no fuzzy matching, stemming, transliteration, pagination, FTS, or separate index.
