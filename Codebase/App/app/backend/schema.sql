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
  CHECK (
    (directionality = 'symmetric' AND direction_from IS NULL) OR
    (directionality = 'directional' AND direction_from IN (person_a, person_b))
  )
);

CREATE INDEX IF NOT EXISTS idx_general_relationships_person
  ON general_relationships(person_a, person_b);

CREATE UNIQUE INDEX IF NOT EXISTS uq_general_rel_symmetric_standard
  ON general_relationships(person_a, person_b, type)
  WHERE directionality = 'symmetric' AND type <> 'custom';

CREATE UNIQUE INDEX IF NOT EXISTS uq_general_rel_symmetric_custom
  ON general_relationships(person_a, person_b, COALESCE(label_a_to_b, ''), COALESCE(label_b_to_a, ''))
  WHERE directionality = 'symmetric' AND type = 'custom';

CREATE UNIQUE INDEX IF NOT EXISTS uq_general_rel_directional_standard
  ON general_relationships(person_a, person_b, type, direction_from)
  WHERE directionality = 'directional' AND type <> 'custom';

CREATE UNIQUE INDEX IF NOT EXISTS uq_general_rel_directional_custom
  ON general_relationships(person_a, person_b, direction_from, COALESCE(label_a_to_b, ''), COALESCE(label_b_to_a, ''))
  WHERE directionality = 'directional' AND type = 'custom';

-- Phase 11: Canonical identity, aliases, and forward schema foundation tables

CREATE TABLE IF NOT EXISTS unresolved_people (
  id TEXT PRIMARY KEY,
  label TEXT,
  notes TEXT,
  created_at TEXT NOT NULL,
  resolved_to_person_id TEXT REFERENCES people(id),
  resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS identifier_aliases (
  id INTEGER PRIMARY KEY,
  old_identifier TEXT NOT NULL UNIQUE,
  canonical_id TEXT NOT NULL,
  entity_type TEXT NOT NULL DEFAULT 'person',
  notes TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_identifier_aliases_canonical
  ON identifier_aliases(canonical_id);

CREATE TABLE IF NOT EXISTS platform_identities (
  id INTEGER PRIMARY KEY,
  person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
  platform TEXT NOT NULL,
  identity_value TEXT NOT NULL,
  is_current INTEGER NOT NULL DEFAULT 1 CHECK (is_current IN (0, 1)),
  notes TEXT,
  created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_platform_identities_person
  ON platform_identities(person_id);

CREATE TABLE IF NOT EXISTS places (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  address TEXT,
  latitude REAL,
  longitude REAL,
  place_type TEXT,
  notes TEXT,
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  date_exact TEXT,
  date_approx TEXT,
  place_id TEXT REFERENCES places(id),
  event_type TEXT,
  notes TEXT,
  created_at TEXT
);
