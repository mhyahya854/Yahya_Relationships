-- People Relationships application schema extensions.
-- All tables from the legacy family schema (created by build_family.py) are
-- preserved untouched; these tables extend the same database.

CREATE TABLE IF NOT EXISTS groups (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  slug TEXT NOT NULL UNIQUE,
  kind TEXT NOT NULL DEFAULT 'custom'
    CHECK (kind IN ('system', 'custom')),
  display_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS person_groups (
  person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
  group_id TEXT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
  PRIMARY KEY (person_id, group_id)
);

CREATE INDEX IF NOT EXISTS idx_person_groups_group
  ON person_groups(group_id);

CREATE TABLE IF NOT EXISTS general_relationships (
  id INTEGER PRIMARY KEY,
  person_a TEXT NOT NULL REFERENCES people(id),
  person_b TEXT NOT NULL REFERENCES people(id),
  type TEXT NOT NULL,
  directionality TEXT NOT NULL DEFAULT 'symmetric'
    CHECK (directionality IN ('symmetric', 'directional')),
  direction_from TEXT,
  label_a_to_b TEXT,
  label_b_to_a TEXT,
  notes TEXT,
  created_at TEXT,
  updated_at TEXT,
  CHECK (person_a <> person_b),
  CHECK (person_a < person_b),
  UNIQUE (person_a, person_b)
);

CREATE INDEX IF NOT EXISTS idx_general_relationships_person
  ON general_relationships(person_a, person_b);
