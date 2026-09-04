# Family Relationships — Project Hard Rules

This is the current project constitution (not a historical raw source
batch). Historical evidence stays in `sources/`.

## 1. Data authority

- `family.db` (SQLite) is the authoritative structured family data store.
- `build_family.py` is the only writer of `family.md` and `family.html`.
- The standalone `family.html` is a generated view; it is never imported back
  as authoritative data.
- `family.json` is an archived migration snapshot only.

## 2. Explicit facts vs derived facts

- Explicit facts (parent-child, marriage, full-sibling statement, birth
  order, gender, birth year, alias, no children, marital status,
  placeholders, deferred/on-hold) are stored in the database.
- Derived facts (mother/father, son/daughter, brother/sister, uncle/aunt,
  nephew/niece, grandparents, cousins, once-removed terms, maternal/paternal
  sides, multiple paths) are calculated at build time. They are never stored
  as if the user supplied them.

## 3. Identity

- One real person = one canonical record = one visible card.
- Aliases do not create people. Typos do not automatically create people.
- Person IDs are stable once created.

## 4. Parent/child semantics

- Parent-child records store the parent, child, role, and kind.
- A layout helper may shape the path; it never replaces the actual parent or
  child card as the semantic endpoint.

## 5. Marriage semantics

- Spouses stay physically adjacent in the diagram.
- The marriage line is direct spouse-to-spouse.
- Child routing is a separate layout concept below the couple.

## 6. Sibling semantics

- Sibling groups record ordered (`[1]`, `[2]`, ...) or unordered statements.
- Full-sibling type exists only when explicitly stated.

## 7. Biological default

- "Has children / have children / their children are ..." means biological by
  default unless an alternative status is explicitly stated.
- Supported kinds: biological, adopted, step, foster, guardian, unknown,
  unspecified.
- Never infer an alternative status.

## 8. Unknown and deferred information

- No children != no children recorded != unknown child status.
- "No children" is stored only when explicitly stated.
- Deferred/on-hold items are legitimate states, not validation failures.
- Do not invent placeholder parents or people.

## 9. Provenance

- Explicit facts are linked to source batches through the `sources` and
  `fact_sources` tables.
- The graph, visual proximity, and derived kinship are never evidence.
- Latest explicit user correction supersedes older structured data; the old
  evidence files stay untouched and a new source batch records the change.

## 10. Visual semantics

- Every real relationship visibly starts/ends at actual person cards.
- Full siblings and other explicit cross-family relations use neutral dotted
  lines with labels only (no repeated names in separate boxes).
- Secondary dotted paths must not overlap marriage lines, parent-child
  lines, other dotted lines, person cards, labels, or visible junctions.

## 11. Layout

- Current master view: maternal generally left, core center, paternal
  generally right; Irsa + Mansoor form the central bridge.
- This is the current master preference, not a universal law for every future
  cross-marriage.
- Same-generation people stay in the same general band when possible.
- Space is not a constraint; readability wins.

## 12. Colors

- Maternal units: subtle pink shades. Paternal units: subtle blue shades.
- Irsa pink, Mansoor blue, neutral shared couple grouping.
- Secondary cross-relations: neutral gray.
- Color is never the only way to understand a relationship.

## 13. Kinship calculation

- Kinship is derived from the explicit biological parent-child graph,
  full-sibling facts, and marriage facts.
- Python is the canonical kinship engine; the browser receives precomputed
  relationship data, so there is one implementation.

## 14. Multiple relationship paths

- Never collapse multiple valid relationships into one.
- Direct relationships display first; remaining cousin paths appear under
  "additional derived relationship paths".

## 15. Perspective mode

- `canonical_focus_person` = Mohammad Yahya Hussain.
- `selected_perspective` is temporary UI state; changing it never changes the
  database or the master graph geometry.

## 16. Photos

- Optional; store only a relative path in the database.
- Photos appear in the detail panel, not inside every Mermaid card.
- Missing photos fall back to initials; never fabricate a photo.

## 17. Offline portability

- `family.html` must work from `file://` without Python, a server, or the
  internet.
- Mermaid is bundled locally/inside the export; no CDN dependency.

## 18. Validation

- Python validates semantic rules even though SQLite has constraints:
  ancestry cycles, unsupported kinds/statuses, single-person marriages,
  no-children contradictions, sibling-group consistency, duplicates,
  provenance integrity, and the derived kinship audit.

## 19. Corrections and conflicts

- Genuine ambiguity: ask one focused question. Never guess.
- Do not send questionnaires; do not repeatedly ask deferred questions.

## 20. Expansion

- Family data grows through the controlled data/source workflow, then a
  rebuild. The app is read-only and never edits family data.
