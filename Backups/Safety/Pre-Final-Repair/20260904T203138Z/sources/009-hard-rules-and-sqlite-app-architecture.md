# Source batch 009

Recorded from Mohammad Yahya Hussain on 2026-09-03. This batch documents an
architecture/hard-rule decision, not new family facts.

- Option A selected: SQLite becomes the structured source of truth after a
  verified migration from the Revision 5 JSON snapshot.
- Python remains the validator, kinship engine, and builder.
- The viewer is plain HTML/CSS/Vanilla JavaScript; no framework.
- One generated standalone portable `family.html` export is produced.
- Arbitrary-person perspective is supported; the canonical focus stays
  Mohammad Yahya Hussain.
- Person-to-person relationship comparison is supported.
- Optional local photos live under `photos/` (relative paths only).
- Permanent hard rules are consolidated in `HARD_RULES.md`.
- Derived kinship is calculated, never stored as user-stated fact.
- No internet is required to view the standalone export.
- The viewer is read-only; family updates continue through the controlled
  data/source workflow.
