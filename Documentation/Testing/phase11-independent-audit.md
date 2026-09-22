# Mosaic Phase 11 — Independent Architectural Audit

> **Decision: FROZEN**
>
> Phase 11 passed independent architectural audit after the repairs recorded
> below. Phase 12 remains not started.

## Audit identity

- Audit model: GPT-5.6 High
- Audit date: 2026-09-22
- Phase 10 baseline: `5e7c75551cd0513e68d6a304050bf508162da4f3`
- Provisional Phase 11 SHA: `666e5640eec797fa8123b341cd606b1654f55475`
- Final SHA: the commit containing this report; the exact remote SHA is
  recorded in the audit completion response because a commit cannot contain
  its own hash.
- Branch: `main`

## Scope and method

The audit reviewed the complete Phase 10-to-Phase 11 change set, searched every
runtime database and filesystem path, read the migration/backup/restore code,
and treated the provisional reports as unverified claims. Mutating, failure-
injection, restore, concurrency, and rerun checks used synthetic temporary Data
Roots. The production Data Root was inspected read-only except for publishing
the repaired canonical artifacts after exact comparison with a clean isolated
migration. No Phase 12 functionality was implemented.

## Findings and repairs

### Critical

1. Canonical-root detection could lose its fail-closed signal and permit a
   missing canonical database to be interpreted as legacy. Canonical layout
   metadata and historical sentinel handling are now coherent, and a known
   canonical root with a missing/corrupt `relationships.db` is rejected without
   fallback or database creation.
2. Migration publication did not have sufficiently explicit recovery behavior
   across all database/People switch points. Publication now uses staged
   assets, an incomplete-operation marker, verified rollback, and deterministic
   recovery; nine injected failure checkpoints prove the legacy source remains
   intact and a clean rerun succeeds.
3. Backup/restore could preserve the wrong layout markers when restoring a
   legacy snapshot over a canonical root. Restore now switches database,
   People, configuration, and `HISTORICAL_FAMILY_DB.md` as one validated layout
   transition and rolls back on post-restore health failure.

### High

1. The provisional migration tests primarily proved row counts rather than
   semantic equality. Independent row-by-row comparison now covers every
   migrated table, meaningful column, null, relationship orientation, source
   reference, group membership, alias, and metadata value after translating
   identifiers.
2. Canonical ID normalization/collision rules were incomplete for accented
   Latin text, non-Latin text, invalid names, duplicate names, concurrent
   creation, and path safety. IDs now use deterministic Latin folding or stable
   `uXXXX` components, bounded counters, strict validation, and transactional
   collision handling.
3. Canonical and legacy schema-version meanings were inconsistent in parts of
   Data Root, backup, restore, and new-root initialization. `APP_SCHEMA_VERSION`
   remains the supported legacy schema, while canonical roots require
   `CANONICAL_SCHEMA_VERSION = 3`; `PRAGMA user_version` and metadata are
   validated together.
4. Several family/general mutation paths did not uniformly accept legacy
   identifiers after migration. Person, parent-child, marriage, sibling-group,
   and general-relationship services now resolve identifier history before
   canonical writes.
5. Canonical backup manifests exposed machine-specific source-root paths and
   restore verification was not sufficiently layout-aware. New manifests are
   portable, schema-aware, and verified for canonical or legacy layout without
   disclosing the absolute source root.

### Medium

1. Facts/about generation invented contact/status timestamps for unknown
   information. The generated files now preserve only known authorized values
   and use `Unknown` for absent identity/status/history fields.
2. Canonical IDs containing `--` were used unsafely as Mermaid subgraph
   identifiers. All emitted Mermaid identifiers are now sanitized, with an
   independent render-safety regression.
3. The Connections information drawer had lost Profile/Family navigation after
   canonical UI fixture changes. The existing frozen interaction is restored
   without redesigning Phase 10.
4. UI regression fixtures assumed legacy paths, legacy IDs, or the old search
   interaction. They now create and exercise isolated canonical schema-3 roots
   while retaining the frozen UI behavior.

### Low

1. Current documentation still contained provisional/model-specific handoff
   wording and ambiguous authority descriptions. It now records permanent,
   model-independent frozen invariants and the audit model only as evidence.
2. Runtime/build/staging by-products were missing focused ignore rules. Ignore
   coverage now includes graph outputs, TypeScript build state, SQLite
   sidecars, and migration staging/rollback paths.

No unresolved critical, high, medium, or low Phase 11 finding remains.

## Canonical database evidence

- Forward authoritative database: `Database/relationships.db`
- SHA-256: `95FAA21CD46A8EE7D64455FE3AA2A881410BF734630F46A51E694B4BA6C41A2C`
- `PRAGMA integrity_check`: `ok`
- `PRAGMA foreign_key_check`: no rows
- `PRAGMA user_version`: `3`
- metadata `app_schema_version`: `3`
- metadata `_source_of_truth`: `relationships.db`
- Runtime connection `PRAGMA foreign_keys`: `1`
- People: 35
- Identifier-history mappings: 35, each targeting an existing canonical person
- `migrate_canonical.py --verify`: `Data Root Health: OK`, `canonical_v3`,
  schema v3, 35 people

`Database/Main/family.db` remains historical provenance. Runtime connection
resolution was independently observed selecting `Database/relationships.db`.
Missing canonical storage raises a structured error and neither falls back to
`family.db` nor creates an empty SQLite file.

## Semantic migration parity

The independent comparator translated all legacy person identifiers through
`identifier_aliases` and compared actual records, not counts:

| Domain | Result |
| --- | --- |
| people | exact meaningful-column parity, 35/35 |
| parent_child | exact endpoints, role, and kind, 44/44 |
| marriages | exact endpoints, status, year, child status, and ordering, 12/12 |
| sibling_groups | exact records, 10/10 |
| sibling_group_members | exact translated membership |
| sources and fact_sources | exact provenance and translated entity keys |
| review_notes | exact |
| groups and person_groups | exact |
| aliases | exact person aliases plus 35 constrained identifier-history rows |
| general_relationships | exact orientation, labels, notes, dates, and direction |
| metadata | exact except the intentional canonical schema/authority/ID values |

Result: semantic row-by-row parity passes with no missing, invented, or
reoriented fact.

## IDs and filesystem evidence

- Known format: `normalized_full_name--INITIALS##`
- Unresolved format: `unknown_person--UP####`
- Duplicate-name counters are scoped to the normalized full name, not merely
  initials.
- Sequential and concurrent duplicate creation cannot duplicate an identity.
- Renaming or adding an alias leaves the assigned canonical ID unchanged.
- Foreign-key and uniqueness constraints reject missing or ambiguous alias
  targets; alias resolution is non-recursive and deterministic.
- Production hierarchy: 1 person under `People/Me`, 34 under
  `People/Family`, 0 under `People/Friends`, and 0 currently unresolved.
- All 35 production person directories contain exactly the two required files
  and five required directories from the approved seven-item template; no
  `Media`, `Voice Notes`, `Chats`, or `Transcripts` substitute exists.
- All 35 legacy journals match their canonical journal byte-for-byte. A
  deterministic concatenated-content SHA-256 over legacy-ID order is
  `8480EC6E77D943FF6E1C3AE70DDFDF86DE66E05AB86EB17F84963545EAE9415B`
  for both trees.
- Facts/about files contain only migrated known values and explicit `Unknown`
  values for absent contact, platform, meeting, status, evidence, and timestamp
  fields.

Fresh isolated migrations also passed Unicode, decomposed accent, punctuation,
non-Latin, spaces, long-path, Windows-safe-name, case-collision, empty-journal,
multilingual-journal, and large-journal checks.

## Atomicity, idempotency, and recovery

Migration is deterministic and safely refuses an already-canonical root without
rewriting the database, People tree, aliases, or journals. Each of these
injected checkpoints failed safely, preserved the legacy DB and journal hashes,
removed unpublished staging state, and then accepted a clean rerun:

1. `before_db_staging`
2. `during_db_migration`
3. `after_db_transformation`
4. `during_folder_staging`
5. `during_journal_copy`
6. `after_validation_before_publish`
7. `after_people_publish_before_db_publish`
8. `during_publication`
9. `during_final_verification`

Runtime access is blocked by an incomplete-operation marker. Temporary staging
and rollback paths are never treated as canonical authority.

## Backup and restore evidence

- The tracked pre-migration safety backup verifies successfully as a
  transactionally consistent SQLite snapshot. Its contract is semantic SQLite
  equivalence, not byte identity with an open source database.
- Its current manifest contains no username, absolute source-root path, temp
  directory, or machine-specific path.
- An isolated canonical backup verified at schema 3, restored to a new empty
  Data Root, reproduced the database and complete People tree, and supported
  subsequent canonical reads and writes without creating a legacy DB.
- The pre-migration legacy backup restores as legacy, is never mislabeled
  canonical, and correctly replaces an existing canonical root without leaving
  canonical sentinels or a split People tree.
- Creation, verification, safety-backup-first restore, rollback, manifest
  tamper detection, long paths, and post-restore health checks pass.

## Runtime authority and family regression

Isolated post-migration mutations covered person create/update, group changes,
journal append, parent-child, marriage, sibling-group, general relationship,
alias input, backup, and restore. Every write landed in
`Database/relationships.db` and canonical `People/`; the legacy DB and
`Database/People` hashes remained unchanged.

The family regression independently compared every meaningful ordered person
pair after ID translation. It confirms 35 people, 44 parent-child facts, 12
marriages, 10 sibling groups, 21 focus-person cousin paths, all arbitrary
perspectives, maternal/paternal direction, degree/removal, and simultaneous
paths. The Markdown/HTML export differences are representational canonical-ID
changes only; visible genealogy is unchanged.

## Data Root, portability, and path safety

Canonical, legacy, first-run, missing, invalid, read-only, moved, restored, and
disconnected roots were exercised. Status inspection is non-mutating; candidate
inspection creates no probe or database. Writable probes use unique files and
always clean up. Missing/corrupt canonical databases fail closed. Internally
generated IDs are validated before filesystem use; absolute IDs, traversal,
reserved Windows components, symlink inputs, and case-colliding folders are
rejected.

Windows runtime/build verification passed. Cross-platform tests cover POSIX
bootstrap paths, spaces/Unicode, cwd independence, case-sensitive behavior,
and target triples. macOS/Linux packaging remains a later release activity,
not a Phase 11 data-architecture blocker.

## Test evidence

All commands were run against the final audited working tree:

- Backend: 534 collected; 533 passed, 1 skipped, 0 failed. The skip is the
  platform-dependent symlink-creation case unavailable on this Windows host.
- Independent Phase 11 audit: 21 passed.
- Canonical verification: PASS (`canonical_v3`, schema 3, 35 people).
- Legacy/family regression: PASS (35 people, 44 parent-child, 12 marriages,
  10 sibling groups, 21 cousin paths, 35 arbitrary perspectives).
- Frontend `npm run typecheck`: PASS.
- Frontend `npm run build`: PASS.
- UI smoke: 15/15 PASS.
- People UI: PASS.
- Relationships UI: PASS.
- Connections redesign regression: PASS with 82-person synthetic graph and 28
  visual checkpoints.
- Family Tree UI: 65/65 PASS.
- Search UI: 42/42 PASS.
- Backups UI: 42/42 PASS.
- Data Root UI: 50/50 PASS.
- Navigation UI: 18/18 PASS.
- `cargo check --locked`: PASS using a fresh temporary target directory after
  detecting a stale path in the old local Cargo cache.
- `cargo test --locked`: PASS; 0 Rust unit tests and 0 doc tests are defined.
- `git diff --check`: PASS at the final staging gate.

## Production integrity

- Historical `Database/Main/family.db` before:
  `3258C738F9D65B23B15970D0E1E7389E8584A35BA8E26030249061BAF74E096E`
- Historical `Database/Main/family.db` after:
  `3258C738F9D65B23B15970D0E1E7389E8584A35BA8E26030249061BAF74E096E`
- `git diff -- Database/People`: empty
- Historical journals: 35; unchanged and byte-equal to canonical journals
- Canonical DB:
  `95FAA21CD46A8EE7D64455FE3AA2A881410BF734630F46A51E694B4BA6C41A2C`
- Canonical People: 35 exact templates; 1 Me + 34 Family

## Source control and privacy

The canonical project data and one pre-upgrade safety snapshot are intentional
tracked project artifacts under the established repository policy. Current
manifests and authoritative documentation were scanned for usernames, absolute
Windows paths, AppData paths, pytest temp paths, and obsolete current-authority
audit wording; none remains. No history rewrite or force push was performed.
Pre-existing user-owned screenshot deletions and `tsconfig.tsbuildinfo` changes
were excluded from the Phase 11 commit.

## Deferred items

Only roadmap work remains deferred: Raw intake/provenance workflows, OCR and
transcription expansion, media/Gallery organization, conversation imports,
memories/flashbacks, location imports, face recognition, expanded Hermes, and
later domain tables introduced through explicit versioned migrations. These are
Phase 12–17 concerns and were not started.

## Freeze decision

Phase 11 is safe to freeze. The application has one verified forward database
authority, the legacy source remains preserved, migration and restore fail
closed, semantic parity is exact, canonical IDs and folder templates satisfy
the Master Plan, and runtime reads/writes remain canonical. Independent
failure, concurrency, backup/restore, portability, family, frontend, UI, and
desktop verification all pass. Later phases may version the canonical schema
only through explicit migrations that preserve these frozen invariants.
