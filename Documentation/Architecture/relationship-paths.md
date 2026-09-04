# Relationship paths — architecture

## One sentence

Every relationship label the canonical engine produces can be "proved" by an
objective graph path returned by the Python backend — and the Relationships
screen renders that path in React Flow when you press **Show why**.

## Data flow

```text
SQLite facts (Database/Main/family.db)
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
    +-> React Flow Relationships screen ("Show why", path focus)
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

## Path JSON shape

Each path contains a deterministic id (hash of domain, semantic type, node
order and edge signature), label (English + Urdu), side/degree/removal where
applicable, common ancestors, ordered `nodes`, typed `edges`
(`parent_child`, `marriage`, `sibling_group`, `general` + subtype), and a
`derived` flag.

## Show why / path focus (frontend)

1. The side panel lists Primary and Additional paths from
   `get_relationship`.
2. **Show why** calls the path endpoint, finds paths whose label matches the
   clicked relationship, and enters path focus mode.
3. React Flow dims everything else, highlights path nodes/edges, adds missing
   path nodes (including virtual "Shared ancestors" nodes) as a temporary
   overlay, fits the path into view and shows a template-generated
   explanation (no LLM).
4. Esc / *Exit path* restores the previous graph state.

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
