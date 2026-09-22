# Relationship paths — architecture

## One sentence

Every relationship label the canonical engine produces can be "proved" by an
objective graph path returned by the Python backend — and the Connections
screen can render several independently selected paths in React Flow.

## Data flow

```text
SQLite facts (Database/relationships.db; legacy roots use Database/Main/family.db before migration)
    |
    v
Canonical Python family engine (Codebase/App/app/backend/domain/family/;
    |   CLI wrapper Codebase/Scripts/build_family.py)
    |   one implementation, used by the legacy export, API, Hermes and UI
    v
Path extraction (domain/relationships/path_service.py)
    |   explicit facts become direct paths;
    |   derived kinship records become concrete ancestor-chain paths
    v
Label layer (kinship/labels.py)
    |   semantic keys (e.g. paternal_cousin_degree_1) + English/Urdu labels
    v
FastAPI (GET /api/relationships/{p}/{t}/paths)
    |
    +-> React Flow Connections screen (multi-target Relationship Explorer)
    +-> Hermes tool get_relationship_paths
```

## Stored facts → canonical Python graph

- `parent_child` rows (with role and kind: biological, adopted, step, foster,
  guardian, unknown, unspecified), `marriages`, `sibling_groups` and
  `general_relationships` are the stored facts.
- The canonical kinship implementation in `Codebase/App/app/backend/domain/family/engine.py`
  (wrapped by `Codebase/Scripts/build_family.py`) builds a biological parent graph, adds calculation-only
  virtual ancestors for full-sibling facts with unrecorded parents, and enumerates ancestor
  chains.
- `Codebase/App/app/backend/domain/family/paths.py` mirrors the engine's
  semantic record enumeration (`_pair_path_records`) but remembers one
  concrete chain pair per deduplicated record, so every engine label has a
  real node/edge path.

## Path extraction rules

- `max_depth` is bounded (default 10, allowed 1–30; engine depth is 30).
- `max_paths` is bounded (default 10, allowed 1–50).
- Paths are canonicalized: the same semantic/structural route is never
  returned twice, and cycles are impossible by construction (ancestor chains
  cannot revisit a person).
- Distinct legitimate paths (for example *paternal first cousin* and
  *maternal second cousin* for the same pair, or a nephew via the maternal
  grandmother versus the maternal grandfather) are preserved.
- Direct relationships (parent, child, spouse, sibling, friend, mentor)
  become one-step (or shared-parent) paths with `derived: false`.
- General relationships are never chained: A friend B and B friend C produce
  no A↔C claim.

## Derived paths are never the source of truth

Path objects are computed on demand from the same model the engine reads.
They are not stored in SQLite, not cached authoritatively, and never mutate
facts. If a family or general relationship write happens, the next path
request simply reads the updated database.

## Canonical display ranking

`services/relationship.py` applies one person-independent ranking function to
pair, list, comparison, and contextual consumers. It presents exactly one calm
default relationship while preserving every other legitimate entry. The key
orders canonical family roles before unrelated general labels, then proof
distance, blood versus affinal character, stored versus derived status when
semantically comparable, degree/removal, side, and stable semantic identifiers.
No name-specific output is hard-coded.

## Path JSON shape

Each path contains a deterministic id (hash of domain, semantic type, node
order and edge signature), label (English + Urdu), side/degree/removal where
applicable, common ancestors, ordered `nodes`, typed `edges`
(`parent_child`, `marriage`, `sibling_group`, `general` + subtype), and a
`derived` flag.

## Relationship Explorer and path focus (frontend)

1. The current Perspective remains the central person. Clicking or searching
   adds target people without replacing that center.
2. Each target card shows the ranked default relationship and additional-role
   count. **Show all relationship paths** is off by default.
3. Turning it on loads canonical paths on demand. Every path has an independent
   checkbox, and each target retains its own selection state.
4. React Flow unions every selected path into one deterministic overlay, adds
   missing path nodes only once, dims unrelated context, and preserves the
   relationship type while applying approved maternal/paternal side shading.
   A shared segment may carry both translucent side treatments; no fabricated
   third relationship color is introduced.
5. Removing one target removes only that target's overlay. Esc clears current
   path emphasis without changing facts, target membership, or the central
   person.

## Family union routing

Family Tree remains genealogy-only. Married people stay separate person nodes
inside a visual union container with a direct spouse-to-spouse marriage line.
Incoming ancestry penetrates that container and ends on the correct individual.
Both spouses feed a distinct shared-child junction for their children. The
container and routing junctions are never semantic relationship endpoints.

## Hermes boundary for future model choice

This phase documents architecture only; it does not implement a model chooser.
Hermes tools consume canonical structured relationship services and must remain
independent of any future LLM/provider/model selection. A future model layer may
explain canonical results, but it must not derive, rank, store, or mutate family
truth. Provider credentials and UI preferences must remain outside the DataRoot
relationship schema.

## Key files

- `Codebase/App/app/backend/domain/family/paths.py` — engine-aligned
  record/path enumeration
- `Codebase/App/app/backend/domain/relationships/path_service.py` — explicit
  + derived path assembly, bounds and errors
- `Codebase/App/app/backend/domain/relationships/graph.py` — neighbour
  expansion model
- `Codebase/App/Frontend/src/features/relationships/` — React Flow graph
  feature
- `Codebase/Tests/Backend/test_paths.py`,
  `Codebase/Tests/Backend/test_api_paths.py` — path guarantees
