# Mosaic Phase 11 — Canonical Data Foundation & Migration Handoff

> **STATUS: PHASE 11 — FROZEN**
>
> Independent architectural audit passed.

## Authority

- Phase 10 baseline: `5e7c75551cd0513e68d6a304050bf508162da4f3`
- Provisional Phase 11 implementation: `666e5640eec797fa8123b341cd606b1654f55475`
- Final audit evidence: [phase11-independent-audit.md](../Testing/phase11-independent-audit.md)
- Forward structured authority: `Database/relationships.db` at schema 3
- Historical provenance: `Database/Main/family.db`, retained byte-for-byte and never used as a canonical fallback

## Frozen invariants

- Known IDs use `normalized_full_name--INITIALS##`; unresolved IDs use
  `unknown_person--UP####`. Assigned IDs do not change when display names do.
- Every legacy person ID resolves through constrained `identifier_aliases` to
  exactly one existing canonical person.
- Canonical roots fail closed if `Database/relationships.db` is missing,
  corrupt, or schema-incoherent. Runtime code never silently creates it.
- Canonical person records live once under `People/Me`, `People/Family`, or
  `People/Friends`; unresolved records live directly under `People/`.
- Each person directory uses the exact seven-item Master Plan template, and
  migrated Journal bytes are preserved exactly.
- Migration publication, backup, restore, move, and new-root initialization
  are validated against canonical schema and filesystem authority.
- `Database/Main/family.db` remains historical evidence, not a second writable
  truth source.

## Continuation boundary

Phase 12 is not started. Later domain tables and features must be introduced by
explicitly versioned migrations that preserve the Phase 11 invariants. No Raw
ingestion, media organization, conversation import, face recognition, or
expanded Hermes work is included in this freeze.
