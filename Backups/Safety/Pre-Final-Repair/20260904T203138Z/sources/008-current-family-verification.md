# Source batch 008

Recorded from Mohammad Yahya Hussain on 2026-09-03 as the evidence for the
revision-5 data/semantic update. Wording is preserved as supplied; the
structured family data is maintained separately in family.json.

## Confirmed family facts

- Abrar Hussain and Israr Hussain are FULL brothers; use `full brothers /
  سگے بھائی` where a distinction is useful. Their parents are not added in
  this phase (later expansion).
- Whether Shahnaz Israr and Shaheen Abrar have any relationship to each other
  is ON HOLD: do not infer or add a relationship, do not remove either person,
  do not ask again during this task.
- Rubinna and Falak Naz are FULL sisters; use `full sisters / سگی بہنیں`.
  Their parents will be added later.
- Mohammad Yahya Hussain (2004) is older than Maham Mansoor (2006); record
  `[1] Mohammad Yahya Hussain`, `[2] Maham Mansoor` (oldest to youngest).
- Ezan Asif (2003) is older than Fakhir Asif (2007); record `[1] Ezan Asif`,
  `[2] Fakhir Asif` using the existing `[1]`, `[2]` visual system, not a long
  birth-order arrow chain.
- Arsalan Israr and Falak Naz are married and have NO children
  (`children_status = no_children`); show `no children / کوئی اولاد نہیں`.
- Ayesha Naeem and Wahaj are married and have NO children. Ayesha's separate
  other-family placeholder stays unchanged; adoption, guardianship, foster
  status, and alternative legal parents are NOT inferred.
- Abrar Hussain and Shaheen Abrar are the BIOLOGICAL parents of
  `[1] Mansoor Hussain`, `[2] Hina`, `[3] Sana`, `[4] Afshan`.
- Aresha Zubair is female; Fizza Zubair is female.
- "Moix" in the latest confirmation refers to the existing canonical person
  Moiz (no new person is created). Fizza Zubair and Moiz are married and have
  NO children.
- Abdul Rafey is currently SINGLE; record a person-level
  `marital_status: single` rather than a fake spouse or empty spouse node.

## Biological-child default policy

- Explicit "has child / have children / they have X children / their children
  are ..." = biological parent-child by default unless the user explicitly
  states an alternative status.
- Explicit alternative status overrides the default.
- Do not infer parentage from visual proximity.
- Absence of children in the data does NOT mean "no children".
- "No children" is recorded only when explicitly stated.
- Normalize the existing user-supported children of Irsa+Mansoor,
  Shahnaz+Israr, Abrar+Shaheen, Sadia+Asif, Hina+Zubair, Aresha+Owais,
  Sana+Sajjad, and Afshan+Adeel Ahmad to biological while preserving recorded
  mother/father/parent roles. Do not invent missing relationships.

## Explicitly no children (this revision)

1. Sohaib Hussain + Rubinna
2. Arsalan Israr + Falak Naz
3. Ayesha Naeem + Wahaj
4. Fizza Zubair + Moiz

These are visibly distinguishable from couples whose child status is merely
unknown. No child junctions are created for them, and no "no children" label
is invented for anyone else.

## Derived relationships (calculate, do not hardcode)

- The software/AI derives kinship from explicit facts; the user is not asked
  to calculate cousin terminology.
- Abrar+Israr full brothers make every biological child of Israr/Shahnaz a
  first cousin of every biological child of Abrar/Shaheen, including
  Irsa Naz + Mansoor Hussain (first cousins AND spouses; both relationships
  are kept).
- Because of the two full-brother grandfathers, some relatives have more than
  one valid relationship path to the focus person, e.g.:
  - Ezan/Fakhir: maternal first cousin AND paternal second cousin.
  - Children of Hina/Sana/Afshan: paternal first cousin AND maternal second
    cousin.
  - Aresha's daughters: paternal first cousin once removed AND maternal second
    cousin once removed.
- Explicit facts and derived facts stay separate; derived facts are never
  written into family.json as user statements.
- Derived display must not create a spiderweb: direct full-sibling/cross lines
  stay dotted; important multiple relationships appear in existing
  unit/annotation text; focus-person cousin paths appear in a generated
  derived-relationships section.

## Still deferred / on hold (not verification failures)

- Parents of Abrar/Israr and Rubinna/Falak; older generations and additional
  predecessors.
- Possible relationship between Shahnaz and Shaheen (on hold).
- Other cross-family/spouse relationships not yet supplied (Asif, Wahaj,
  Zubair, Sajjad, Adeel, Owais, Moiz only when explicitly present later).
- Previous marriages / divorces / remarriages.
- Future cousins/branches not yet supplied.

After the current in-scope tree is fully verified, one next-generation
predecessor question may be asked (one question, then stop).
