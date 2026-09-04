import argparse
import html as html_module
import json
import sqlite3
from collections import defaultdict
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parent
CODEBASE_DIR = SCRIPTS_DIR.parent
REPO_ROOT = CODEBASE_DIR.parent

DATA_PATH = REPO_ROOT / "Database" / "Main" / "family.json"
DB_PATH = REPO_ROOT / "Database" / "Main" / "family.db"
ARCHIVE_DIR = REPO_ROOT / "Documentation" / "Archive"
ARCHIVE_JSON_PATH = ARCHIVE_DIR / "family-revision-5-pre-sqlite.json"
VENDOR_DIR = CODEBASE_DIR / "Resources" / "Vendor"
MERMAID_LIB_PATH = VENDOR_DIR / "mermaid.min.js"
OUTPUT_MD_PATH = REPO_ROOT / "Database" / "Exports" / "Family" / "family.md"
OUTPUT_HTML_PATH = REPO_ROOT / "Database" / "Exports" / "Family" / "family.html"

ALLOWED_PARENT_KINDS = {
    "biological",
    "unspecified",
    "adopted",
    "foster",
    "guardian",
    "step",
    "unknown",
}
ALLOWED_MARITAL_STATUSES = {"single"}
ALLOWED_MARRIAGE_CHILD_STATUSES = {"no_children", "unknown"}


# ---------------------------------------------------------------------------
# Data loading / validation
# ---------------------------------------------------------------------------


def load_data():
    """Normal data source: family.db (SQLite). Legacy JSON is used only as a
    pre-migration fallback and never silently updated."""
    if DB_PATH.exists():
        return read_sqlite_model(DB_PATH)
    if DATA_PATH.exists():
        return json.loads(DATA_PATH.read_text(encoding="utf-8"))
    raise FileNotFoundError(
        "No family.db or family.json found in the project directory."
    )


def validate(data):
    errors = []
    people = data.get("people", [])
    ids = [person.get("id") for person in people]
    known = set(ids)
    singles = set()

    if len(ids) != len(known):
        errors.append("Person IDs must be unique.")
    if None in known or "" in known:
        errors.append("Every person needs a non-empty ID.")

    for person in people:
        if not person.get("name"):
            errors.append(f"{person.get('id', '<unknown>')} has no name.")
        year = person.get("birth_year")
        if year is not None and (not isinstance(year, int) or not 1800 <= year <= 2100):
            errors.append(f"{person['id']} has an invalid birth year: {year!r}.")
        marital_status = person.get("marital_status")
        if marital_status is not None and marital_status not in ALLOWED_MARITAL_STATUSES:
            errors.append(
                f"{person['id']} has unsupported marital_status: {marital_status!r}."
            )
        if marital_status == "single":
            singles.add(person["id"])

    parent_pairs = set()
    children = {}
    for rel in data.get("parent_child", []):
        parent, child = rel.get("parent"), rel.get("child")
        if parent not in known or child not in known:
            errors.append(f"Unknown person in parent relationship: {parent!r} -> {child!r}.")
            continue
        if parent == child:
            errors.append(f"A person cannot be their own parent: {parent}.")
        pair = (parent, child)
        if pair in parent_pairs:
            errors.append(f"Duplicate parent relationship: {parent} -> {child}.")
        parent_pairs.add(pair)
        children.setdefault(parent, []).append(child)
        kind = rel.get("kind")
        if kind not in ALLOWED_PARENT_KINDS:
            errors.append(
                f"Parent-child {parent} -> {child} has unsupported kind: {kind!r}."
            )

    visiting, visited = set(), set()

    def visit(person_id):
        if person_id in visiting:
            errors.append(f"Ancestry cycle detected at {person_id}.")
            return
        if person_id in visited:
            return
        visiting.add(person_id)
        for child_id in children.get(person_id, []):
            visit(child_id)
        visiting.remove(person_id)
        visited.add(person_id)

    for person_id in known:
        visit(person_id)

    marriage_pairs = set()
    for rel in data.get("marriages", []):
        first, second = rel.get("person1"), rel.get("person2")
        if first not in known or second not in known:
            errors.append(f"Unknown person in marriage: {first!r} -- {second!r}.")
            continue
        if first == second:
            errors.append(f"A person cannot be married to themselves: {first}.")
        pair = tuple(sorted((first, second)))
        if pair in marriage_pairs:
            errors.append(f"Duplicate marriage: {first} -- {second}.")
        marriage_pairs.add(pair)
        year = rel.get("year")
        if year is not None and (not isinstance(year, int) or not 1800 <= year <= 2100):
            errors.append(f"Marriage {first} -- {second} has an invalid year: {year!r}.")
        child_status = rel.get("children_status")
        if child_status is not None and child_status not in ALLOWED_MARRIAGE_CHILD_STATUSES:
            errors.append(
                f"Marriage {first} -- {second} has unsupported children_status: "
                f"{child_status!r}."
            )
        if child_status == "no_children":
            for spouse in (first, second):
                if spouse in children:
                    errors.append(
                        f"No-children marriage {first} -- {second} has a recorded "
                        f"child of {spouse}."
                    )
        if first in singles or second in singles:
            errors.append(
                f"A person marked single appears in a marriage: {first!r} -- {second!r}."
            )

    group_ids = set()
    for group in data.get("sibling_groups", []):
        group_id = group.get("id")
        if group_id in group_ids:
            errors.append(f"Duplicate sibling-group ID: {group_id}.")
        group_ids.add(group_id)
        members = group.get("members", [])
        if len(members) < 2:
            errors.append(f"Sibling group {group_id} needs at least two members.")
        if len(members) != len(set(members)):
            errors.append(f"Sibling group {group_id} repeats a person.")
        for member in members:
            if member not in known:
                errors.append(f"Sibling group {group_id} references unknown person {member!r}.")
        group_type = group.get("type")
        if group_type is not None and group_type != "full":
            errors.append(
                f"Sibling group {group_id} has unsupported type: {group_type!r}."
            )
        if group_type == "full" and len(members) != 2:
            errors.append(f"Full-sibling group {group_id} must have exactly two members.")

    focus = data.get("metadata", {}).get("focus_person")
    if focus not in known:
        errors.append(f"Unknown focus person: {focus!r}.")

    if errors:
        raise ValueError("\n".join(f"- {error}" for error in errors))


# ---------------------------------------------------------------------------
# SQLite persistence (family.db is the authoritative structured store)
# ---------------------------------------------------------------------------

SOURCE_KIND_BY_BATCH = {
    1: "evidence",
    2: "evidence",
    3: "visual",
    4: "visual",
    5: "visual",
    6: "visual",
    7: "visual",
    8: "evidence",
    9: "architecture",
}
SOURCE_TITLES = {
    "001": "Initial family notes",
    "002": "Review responses",
    "003": "Layout preference",
    "004": "Couple layout and colors",
    "005": "Direct secondary relationship lines",
    "006": "Current master left-right layout",
    "007": "Person-square semantic endpoints",
    "008": "Current family verification",
    "009": "Hard rules and SQLite app architecture",
}
SOURCE_RECORDED_DATES = {
    "001": "2026-09-02",
    "002": "2026-09-02",
    "003": "2026-09-02",
    "004": "2026-09-02",
    "005": "2026-09-02",
    "006": "2026-09-02",
    "007": "2026-09-03",
    "008": "2026-09-03",
    "009": "2026-09-03",
}


def _source_kind(batch_number):
    try:
        return SOURCE_KIND_BY_BATCH.get(int(batch_number), "architecture")
    except ValueError:
        return "architecture"


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sources (
  id INTEGER PRIMARY KEY,
  batch_number TEXT NOT NULL UNIQUE,
  file_path TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'evidence'
    CHECK (kind IN ('evidence', 'visual', 'architecture')),
  recorded_on TEXT
);
CREATE TABLE IF NOT EXISTS people (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  birth_year INTEGER CHECK (birth_year IS NULL OR birth_year BETWEEN 1800 AND 2100),
  gender TEXT CHECK (gender IS NULL OR gender IN ('male', 'female', 'unknown')),
  marital_status TEXT CHECK (marital_status IS NULL OR marital_status IN ('single')),
  branch TEXT,
  legacy_relation_en TEXT,
  legacy_relation_ur TEXT,
  note_en TEXT,
  note_ur TEXT,
  photo_path TEXT,
  display_order INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS aliases (
  person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
  alias TEXT NOT NULL,
  display_order INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (person_id, alias)
);
CREATE TABLE IF NOT EXISTS parent_child (
  id INTEGER PRIMARY KEY,
  parent_id TEXT NOT NULL REFERENCES people(id),
  child_id TEXT NOT NULL REFERENCES people(id),
  role TEXT NOT NULL CHECK (role IN ('mother', 'father', 'parent', 'unknown')),
  kind TEXT NOT NULL
    CHECK (kind IN ('biological', 'adopted', 'step', 'foster', 'guardian',
                    'unknown', 'unspecified')),
  UNIQUE (parent_id, child_id),
  CHECK (parent_id <> child_id)
);
CREATE TABLE IF NOT EXISTS marriages (
  id INTEGER PRIMARY KEY,
  spouse_a TEXT NOT NULL REFERENCES people(id),
  spouse_b TEXT NOT NULL REFERENCES people(id),
  status TEXT NOT NULL DEFAULT 'married'
    CHECK (status IN ('married', 'divorced', 'widowed', 'unknown')),
  year INTEGER CHECK (year IS NULL OR year BETWEEN 1800 AND 2100),
  children_status TEXT
    CHECK (children_status IS NULL OR children_status IN ('no_children', 'unknown')),
  display_order INTEGER NOT NULL,
  CHECK (spouse_a < spouse_b),
  UNIQUE (spouse_a, spouse_b)
);
CREATE TABLE IF NOT EXISTS sibling_groups (
  id TEXT PRIMARY KEY,
  is_ordered INTEGER NOT NULL CHECK (is_ordered IN (0, 1)),
  type TEXT CHECK (type IS NULL OR type IN ('full')),
  label_en TEXT,
  label_ur TEXT,
  display_order INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sibling_group_members (
  group_id TEXT NOT NULL REFERENCES sibling_groups(id) ON DELETE CASCADE,
  person_id TEXT NOT NULL REFERENCES people(id),
  member_order INTEGER CHECK (member_order IS NULL OR member_order >= 1),
  PRIMARY KEY (group_id, person_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sibling_member_order
  ON sibling_group_members(group_id, member_order)
  WHERE member_order IS NOT NULL;
CREATE TABLE IF NOT EXISTS review_notes (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL
    CHECK (status IN ('resolved', 'open', 'placeholder', 'deferred')),
  text TEXT NOT NULL,
  display_order INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS fact_sources (
  id INTEGER PRIMARY KEY,
  source_id INTEGER NOT NULL REFERENCES sources(id),
  entity_type TEXT NOT NULL,
  entity_key TEXT NOT NULL,
  note TEXT,
  UNIQUE (source_id, entity_type, entity_key)
);
CREATE INDEX IF NOT EXISTS idx_fact_sources_lookup
  ON fact_sources(entity_type, entity_key);
"""


def create_sqlite_schema(connection):
    connection.executescript(SCHEMA_SQL)


def _connect(db_path):
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _register_sources(connection, data):
    for file_path in data["metadata"].get("source_batches", []):
        batch_number = Path(file_path).stem.split("-")[0]
        connection.execute(
            """
            INSERT OR IGNORE INTO sources
              (batch_number, file_path, title, kind, recorded_on)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                batch_number,
                file_path,
                SOURCE_TITLES.get(batch_number, f"Source batch {batch_number}"),
                _source_kind(batch_number),
                SOURCE_RECORDED_DATES.get(batch_number),
            ),
        )


def _register_project_source_files(connection):
    """Idempotently register every numbered source file found on disk so the
    database and the evidence folder stay in sync."""
    for file_path in sorted((ROOT / "sources").glob("*.md")):
        batch_number = file_path.stem.split("-")[0]
        if not batch_number.isdigit():
            continue
        connection.execute(
            """
            INSERT OR IGNORE INTO sources
              (batch_number, file_path, title, kind, recorded_on)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                batch_number,
                str(file_path.relative_to(ROOT)).replace("\\", "/"),
                SOURCE_TITLES.get(batch_number, f"Source batch {batch_number}"),
                _source_kind(batch_number),
                SOURCE_RECORDED_DATES.get(batch_number),
            ),
        )


def _fact_source_rules(data):
    """Provenance rules mapping current facts to evidence batches.

    Batch 001 established the initial notes; 002 contains the review
    responses (R1-R8); 008 is the current verification batch that restates
    and corrects the in-scope facts. Batches 003-007 are visual-only and are
    never cited as fact evidence.
    """
    rules = {}

    def add(entity_type, entity_key, *batches):
        rules[(entity_type, entity_key)] = set(batches)

    for person in data["people"]:
        add("people", person["id"], 1, 8)
        for alias in person.get("aliases", []):
            add("aliases", f"{person['id']}|{alias}", 1, 2)

    core_children = {"mohammad_yahya_hussain", "maham_mansoor"}
    maternal_children = {
        "sohaib_hussain",
        "sadia_asif",
        "irsa_naz",
        "arsalan_israr",
        "ayesha_naeem",
    }
    abrar_children = {"mansoor_hussain", "hina", "sana", "afshan"}
    asif_children = {"ezan_asif", "fakhir_asif"}
    hina_children = {"aresha_zubair", "fizza_zubair", "abdul_rafey"}
    unnamed_daughters = {"aresha_owais_daughter_a", "aresha_owais_daughter_b"}
    sana_children = {"muaaz", "barirah"}
    afshan_children = {"musabiha", "musa"}

    child_batches = {}
    for child in core_children:
        child_batches[child] = (1, 2, 8)
    for child in maternal_children:
        child_batches[child] = (1, 2, 8)
    for child in abrar_children:
        child_batches[child] = (2, 8)
    for child in asif_children:
        child_batches[child] = (1, 8)
    for child in hina_children:
        child_batches[child] = (1, 8)
    for child in unnamed_daughters:
        child_batches[child] = (1, 2, 8)
    for child in sana_children:
        child_batches[child] = (1, 8)
    for child in afshan_children:
        child_batches[child] = (1, 2, 8)

    for rel in data["parent_child"]:
        parent, child = rel["parent"], rel["child"]
        add(
            "parent_child",
            f"{parent}|{child}",
            *child_batches.get(child, (1, 8)),
        )

    for marriage in data["marriages"]:
        pair = tuple(sorted((marriage["person1"], marriage["person2"])))
        key = f"{pair[0]}|{pair[1]}"
        if pair in {
            tuple(sorted(("irsa_naz", "mansoor_hussain"))),
            tuple(sorted(("shahnaz_israr", "israr_hussain"))),
            tuple(sorted(("shaheen_abrar", "abrar_hussain"))),
        }:
            add("marriages", key, 2, 8)
        else:
            add("marriages", key, 1, 8)

    group_batches = {
        "mohammad_maham": (8,),
        "maternal_siblings": (1, 2, 8),
        "ezan_fakhir": (8,),
        "rubinna_falak": (1, 8),
        "abrar_israr": (1, 8),
        "paternal_siblings": (1, 8),
        "hina_children": (1, 8),
        "sana_children": (1, 8),
        "afshan_children": (1, 2, 8),
        "aresha_children": (1, 2, 8),
    }
    for group in data["sibling_groups"]:
        group_id = group["id"]
        add("sibling_groups", group_id, *group_batches.get(group_id, (1, 8)))
        for member in group["members"]:
            add("sibling_group_members", f"{group_id}|{member}", *(group_batches.get(group_id, (1, 8))))

    for note in data.get("review_notes", []):
        batch = 2 if note["id"].startswith("R") and note["id"][1:].isdigit() and int(note["id"][1:]) <= 8 else 8
        add("review_notes", note["id"], batch)
    return rules


def import_json_to_sqlite(connection, data):
    create_sqlite_schema(connection)
    _register_sources(connection, data)

    for index, person in enumerate(data["people"]):
        connection.execute(
            """
            INSERT INTO people (
              id, name, birth_year, gender, marital_status, branch,
              legacy_relation_en, legacy_relation_ur, note_en, note_ur,
              photo_path, display_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                person["id"],
                person["name"],
                person.get("birth_year"),
                person.get("gender"),
                person.get("marital_status"),
                person.get("branch"),
                person.get("relation_en"),
                person.get("relation_ur"),
                person.get("note_en"),
                person.get("note_ur"),
                person.get("photo_path"),
                index,
            ),
        )
        for alias_index, alias in enumerate(person.get("aliases", [])):
            connection.execute(
                "INSERT INTO aliases (person_id, alias, display_order) VALUES (?, ?, ?)",
                (person["id"], alias, alias_index),
            )

    for rel in data["parent_child"]:
        connection.execute(
            "INSERT INTO parent_child (parent_id, child_id, role, kind) VALUES (?, ?, ?, ?)",
            (rel["parent"], rel["child"], rel.get("role", "parent"), rel.get("kind", "biological")),
        )

    for index, marriage in enumerate(data["marriages"]):
        spouse_a, spouse_b = sorted((marriage["person1"], marriage["person2"]))
        connection.execute(
            """
            INSERT INTO marriages (
              spouse_a, spouse_b, status, year, children_status, display_order
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                spouse_a,
                spouse_b,
                marriage.get("status", "married"),
                marriage.get("year"),
                marriage.get("children_status"),
                index,
            ),
        )

    for index, group in enumerate(data["sibling_groups"]):
        connection.execute(
            """
            INSERT INTO sibling_groups (
              id, is_ordered, type, label_en, label_ur, display_order
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                group["id"],
                1 if group.get("ordered") else 0,
                group.get("type"),
                group.get("label_en"),
                group.get("label_ur"),
                index,
            ),
        )
        for member_index, member in enumerate(group.get("members", []), start=1):
            connection.execute(
                """
                INSERT INTO sibling_group_members (group_id, person_id, member_order)
                VALUES (?, ?, ?)
                """,
                (group["id"], member, member_index),
            )

    for index, note in enumerate(data.get("review_notes", [])):
        connection.execute(
            "INSERT INTO review_notes (id, status, text, display_order) VALUES (?, ?, ?, ?)",
            (note["id"], note["status"], note["text"], index),
        )

    source_by_batch = {
        row["batch_number"]: row["id"]
        for row in connection.execute("SELECT id, batch_number FROM sources")
    }
    for (entity_type, entity_key), batches in _fact_source_rules(data).items():
        for batch in sorted(batches):
            batch_key = f"{batch:03d}"
            source_id = source_by_batch.get(batch_key)
            if source_id is None:
                continue
            connection.execute(
                """
                INSERT OR IGNORE INTO fact_sources (source_id, entity_type, entity_key)
                VALUES (?, ?, ?)
                """,
                (source_id, entity_type, entity_key),
            )

    metadata = data["metadata"]
    for key, value in metadata.items():
        if key == "source_batches":
            continue
        connection.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            (key, json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value),
        )
    connection.execute(
        "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
        ("_source_of_truth", "family.db"),
    )


def read_sqlite_model(db_path):
    connection = _connect(db_path)
    try:
        metadata = {}
        for row in connection.execute("SELECT key, value FROM metadata"):
            key, value = row["key"], row["value"]
            if key.startswith("_"):
                continue
            if key == "revision":
                metadata[key] = int(value)
            else:
                metadata[key] = value
        metadata["source_batches"] = [
            row["file_path"]
            for row in connection.execute(
                "SELECT file_path FROM sources ORDER BY id"
            )
        ]

        people = []
        for row in connection.execute(
            "SELECT * FROM people ORDER BY display_order, id"
        ):
            person = {
                "id": row["id"],
                "name": row["name"],
                "branch": row["branch"],
                "relation_en": row["legacy_relation_en"],
                "relation_ur": row["legacy_relation_ur"],
                "note_en": row["note_en"],
                "note_ur": row["note_ur"],
            }
            for key in ("birth_year", "gender", "marital_status", "photo_path"):
                if row[key] is not None:
                    person[key] = row[key]
            aliases = [
                alias_row["alias"]
                for alias_row in connection.execute(
                    """
                    SELECT alias FROM aliases
                    WHERE person_id = ? ORDER BY display_order
                    """,
                    (row["id"],),
                )
            ]
            if aliases:
                person["aliases"] = aliases
            people.append(person)

        parent_child = [
            {
                "parent": row["parent_id"],
                "child": row["child_id"],
                "role": row["role"],
                "kind": row["kind"],
            }
            for row in connection.execute(
                "SELECT * FROM parent_child ORDER BY id"
            )
        ]

        marriages = []
        for row in connection.execute(
            "SELECT * FROM marriages ORDER BY display_order, id"
        ):
            marriage = {
                "person1": row["spouse_a"],
                "person2": row["spouse_b"],
                "status": row["status"],
            }
            if row["year"] is not None:
                marriage["year"] = row["year"]
            if row["children_status"] is not None:
                marriage["children_status"] = row["children_status"]
            marriages.append(marriage)

        sibling_groups = []
        for row in connection.execute(
            "SELECT * FROM sibling_groups ORDER BY display_order, id"
        ):
            members = [
                member_row["person_id"]
                for member_row in connection.execute(
                    """
                    SELECT person_id FROM sibling_group_members
                    WHERE group_id = ? ORDER BY member_order, person_id
                    """,
                    (row["id"],),
                )
            ]
            group = {
                "id": row["id"],
                "members": members,
                "ordered": bool(row["is_ordered"]),
                "label_en": row["label_en"],
                "label_ur": row["label_ur"],
            }
            if row["type"] is not None:
                group["type"] = row["type"]
            sibling_groups.append(group)

        review_notes = [
            {"id": row["id"], "status": row["status"], "text": row["text"]}
            for row in connection.execute(
                "SELECT * FROM review_notes ORDER BY display_order, id"
            )
        ]
        return {
            "metadata": metadata,
            "people": people,
            "parent_child": parent_child,
            "marriages": marriages,
            "sibling_groups": sibling_groups,
            "review_notes": review_notes,
        }
    finally:
        connection.close()


def _canonical_person(person):
    return (
        person["id"],
        person.get("name"),
        person.get("birth_year"),
        person.get("gender"),
        person.get("marital_status"),
        person.get("branch"),
        person.get("relation_en"),
        person.get("relation_ur"),
        person.get("note_en"),
        person.get("note_ur"),
        person.get("photo_path"),
        tuple(person.get("aliases", [])),
    )


def _canonical_model(data):
    metadata = dict(data.get("metadata", {}))
    source_batches = tuple(metadata.pop("source_batches", []))
    canonical_metadata = tuple(
        sorted((key, str(value)) for key, value in metadata.items())
    )
    people = sorted(_canonical_person(person) for person in data["people"])
    parent_child = sorted(
        (rel["parent"], rel["child"], rel.get("role"), rel.get("kind"))
        for rel in data["parent_child"]
    )
    marriages = sorted(
        (
            tuple(sorted((rel["person1"], rel["person2"]))),
            rel.get("status"),
            rel.get("year"),
            rel.get("children_status"),
        )
        for rel in data["marriages"]
    )
    sibling_groups = sorted(
        (
            group["id"],
            tuple(group["members"]),
            bool(group.get("ordered")),
            group.get("type"),
            group.get("label_en"),
            group.get("label_ur"),
        )
        for group in data["sibling_groups"]
    )
    review_notes = sorted(
        (note["id"], note.get("status"), note.get("text"))
        for note in data.get("review_notes", [])
    )
    return {
        "metadata": canonical_metadata,
        "source_batches": source_batches,
        "people": people,
        "parent_child": parent_child,
        "marriages": marriages,
        "sibling_groups": sibling_groups,
        "review_notes": review_notes,
    }


def model_parity_report(json_data, db_data):
    """Compare every explicit fact in the JSON model against the SQLite
    read-back model. Returns (equal, [difference strings])."""
    differences = []
    json_model = _canonical_model(json_data)
    db_model = _canonical_model(db_data)
    for section in (
        "metadata",
        "source_batches",
        "people",
        "parent_child",
        "marriages",
        "sibling_groups",
        "review_notes",
    ):
        if json_model[section] != db_model[section]:
            differences.append(
                f"{section}: JSON and SQLite models differ."
            )
    if differences:
        return False, differences
    counts = {
        "people": len(json_data["people"]),
        "parent_child": len(json_data["parent_child"]),
        "marriages": len(json_data["marriages"]),
        "sibling_groups": len(json_data["sibling_groups"]),
        "review_notes": len(json_data.get("review_notes", [])),
    }
    return True, counts


def migrate_json_to_sqlite(json_path, force=False):
    json_data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    validate(json_data)

    connection = None
    try:
        if DB_PATH.exists() and DB_PATH.stat().st_size > 0 and not force:
            connection = _connect(DB_PATH)
            existing = connection.execute(
                "SELECT COUNT(*) AS count FROM sqlite_master "
                "WHERE type = 'table' AND name = 'people'"
            ).fetchone()["count"]
            if existing:
                person_count = connection.execute(
                    "SELECT COUNT(*) AS count FROM people"
                ).fetchone()["count"]
                if person_count:
                    raise RuntimeError(
                        "family.db already contains data. Re-run with --force "
                        "to rebuild it from the JSON migration source."
                    )
            connection.close()
            connection = None
        if DB_PATH.exists() and force:
            DB_PATH.unlink()
        connection = _connect(DB_PATH)
        create_sqlite_schema(connection)
        import_json_to_sqlite(connection, json_data)
        connection.commit()
        connection.close()
        connection = None

        db_data = read_sqlite_model(DB_PATH)
        equal, detail = model_parity_report(json_data, db_data)
        if not equal:
            raise ValueError(
                "Migration parity failed:\n" + "\n".join(detail)
            )
        print("SQLite migration complete. JSON <=> SQLite parity: PASS")
        for label, count in detail.items():
            print(f"- {label}: {count}")
        return detail
    finally:
        if connection is not None:
            connection.close()


# ---------------------------------------------------------------------------
# Small data helpers used by the Mermaid builder
# ---------------------------------------------------------------------------


def mermaid_escape(value):
    """Escape characters that would break a quoted Mermaid label."""
    return str(value).replace("&", "&amp;").replace('"', "&quot;")


def _couple_key(marriage):
    return tuple(sorted((marriage["person1"], marriage["person2"])))


def _cluster_id(couple_key):
    """ID of a couple's layout cluster (the colored couple unit)."""
    return f"u_{couple_key[0]}__{couple_key[1]}"


def _junction_id(couple_key):
    """ID of a layout-only family junction below a couple that has children."""
    return f"j_{couple_key[0]}__{couple_key[1]}"


def _person_node_id(person_id):
    return f"p_{person_id}"


def _route_node_id(group_id):
    """Layout-only routing helper for one secondary relationship.

    This node is not a person or relationship fact and is never visible.
    """
    return f"x_{group_id}"


def _order_markers(data):
    """Small [1], [2], ... indicators from ordered sibling groups."""
    markers = {}
    for group in data.get("sibling_groups", []):
        if not group.get("ordered"):
            continue
        members = group.get("members", [])
        for index, member in enumerate(members, start=1):
            if member not in markers:
                markers[member] = index
    return markers


def _ordered_children(data, children):
    """Birth order for a couple's children when an ordered sibling group states it."""
    child_set = set(children)
    for group in data.get("sibling_groups", []):
        members = group.get("members", [])
        if group.get("ordered") and len(members) >= 2 and set(members) == child_set:
            return list(members)
    return list(children)


def _couple_records(data):
    """Return rendering records derived only from real family facts."""
    people_index = {person["id"]: person for person in data["people"]}
    rels = data["parent_child"]

    parents_of = defaultdict(list)
    for rel in rels:
        parents_of[rel["child"]].append(rel["parent"])

    marriages_by_key = {}
    couples_in_order = []
    for marriage in data["marriages"]:
        key = _couple_key(marriage)
        couples_in_order.append((key, marriage))
        marriages_by_key[key] = marriage

    # A child is routed through a couple's junction only when BOTH recorded
    # parents are exactly that married couple. Any other parent-child fact
    # stays a direct edge (none in current data; kept as a safety path).
    children_by_couple = {}
    child_to_couple = {}
    for key, _ in couples_in_order:
        spouse_set = set(key)
        children = []
        seen = set()
        for rel in rels:
            child = rel["child"]
            if rel["parent"] in spouse_set and child not in seen:
                if set(parents_of[child]) == spouse_set:
                    seen.add(child)
                    children.append(child)
        ordered = _ordered_children(data, children)
        children_by_couple[key] = ordered
        for child in ordered:
            child_to_couple[child] = key

    # Spouse -> couple key, for people who are inside a couple cluster.
    couple_of_person = {}
    for key, _ in couples_in_order:
        for spouse in key:
            couple_of_person[spouse] = key

    return (
        people_index,
        couples_in_order,
        marriages_by_key,
        children_by_couple,
        child_to_couple,
        couple_of_person,
        parents_of,
        rels,
    )


def _person_depths(data, parents_of):
    """Generation depth based only on recorded parent-child facts."""
    cache = {}

    def depth(person_id):
        if person_id in cache:
            return cache[person_id]
        parents = parents_of.get(person_id)
        if not parents:
            cache[person_id] = 0
        else:
            cache[person_id] = 1 + max(depth(parent) for parent in parents)
        return cache[person_id]

    for person in data["people"]:
        depth(person["id"])
    return cache


def _couple_sort_keys(couples_in_order, depths, markers, branch_by_couple):
    """Current-master layout order: maternal, bridge, then paternal."""
    def position(person_id):
        return markers.get(person_id, 10**9)

    def key(couple_entry):
        couple_key, _ = couple_entry
        depth = max(depths[spouse] for spouse in couple_key)
        branch = branch_by_couple[couple_key]
        branch_position = {
            MATERNAL: 0,
            BRIDGE: 1,
            PATERNAL: 2,
            "neutral": 3,
        }[branch]
        smallest_position = min(position(spouse) for spouse in couple_key)
        return (depth, branch_position, smallest_position, couple_key)

    return sorted(couples_in_order, key=key)


# ---------------------------------------------------------------------------
# Visual branch / color helpers (rendering metadata only, never written back)
# ---------------------------------------------------------------------------


MATERNAL = "maternal"
PATERNAL = "paternal"
BRIDGE = "bridge"


def _person_side(person_id, people_index, parents_of, cache):
    """Side (maternal/paternal) a person belongs to, derived from family facts.

    Returns a set; core descendants of Irsa + Mansoor return both sides.
    This is layout metadata for couple coloring, never a family fact.
    """
    if person_id in cache:
        return cache[person_id]
    person = people_index[person_id]
    branch = person.get("branch")
    if branch in (MATERNAL, PATERNAL):
        cache[person_id] = {branch}
        return cache[person_id]
    parents = parents_of.get(person_id)
    if parents:
        sides = set()
        for parent in parents:
            sides.update(_person_side(parent, people_index, parents_of, cache))
        cache[person_id] = sides
        return cache[person_id]
    cache[person_id] = set()
    return cache[person_id]


def _couple_visual_branch(couple_key, people_index, parents_of, side_cache):
    sides = set()
    for spouse in couple_key:
        sides.update(_person_side(spouse, people_index, parents_of, side_cache))
    if sides == {MATERNAL, PATERNAL}:
        return BRIDGE
    if sides == {MATERNAL}:
        return MATERNAL
    if sides == {PATERNAL}:
        return PATERNAL
    return "neutral"


# Pale, non-saturated couple-unit colors. The palette index is the couple's
# position in the structured data's marriage order for its branch, so rebuilds are
# deterministic and existing couples keep their shade until the data file
# itself is reordered. Color is a secondary readability aid only.
MATERNAL_PALETTE = [
    ("#FFF5F7", "#E0B0BD"),  # very pale pink
    ("#FFE9EF", "#DBA3B4"),  # blush
    ("#FFE1EA", "#D88BA5"),  # pale rose
    ("#F7E3E8", "#C992A3"),  # dusty pink
    ("#FFF0EA", "#DCA18E"),  # very light salmon-pink
]

PATERNAL_PALETTE = [
    ("#EEF4FF", "#A8C3E6"),  # pale blue
    ("#E1EEFF", "#97B6DE"),  # powder blue
    ("#E3F1F8", "#8FBBD5"),  # soft sky blue
    ("#E7EDF6", "#9FB3CD"),  # pale steel blue
    ("#ECF0F7", "#A5B2C7"),  # light blue-gray
    ("#E0F2F5", "#8EBECB"),  # very pale cyan-blue
]

NEUTRAL_COUPLE = ("#F7F7FA", "#B4B4CC")


# ---------------------------------------------------------------------------
# Mermaid diagram
# ---------------------------------------------------------------------------


def _person_label(person, marker):
    name = person["name"]
    aliases = person.get("aliases") or []
    if aliases:
        name += " / " + " / ".join(aliases)
    if person.get("birth_year") is not None:
        name += f" ({person['birth_year']})"

    relation_en = person.get("relation_en")
    relation_ur = person.get("relation_ur")
    if relation_en and relation_ur:
        relation = f"{relation_en} / {relation_ur}"
    else:
        relation = relation_en or relation_ur or "Unknown / نامعلوم"

    lines = [f"{f'[{marker}] ' if marker else ''}{name}", relation]
    if person.get("marital_status") == "single":
        lines.append("Single / غیر شادی شدہ")
    if person.get("note_en"):
        lines.append(person["note_en"])
    if person.get("note_ur"):
        lines.append(person["note_ur"])
    return mermaid_escape("<br/>".join(lines))


def _marriage_status_line(marriage):
    year = marriage.get("year")
    if year is not None:
        return f"married {year} / شادی {year}"
    return "married / شادی شدہ"


def _marriage_label(marriage, extra_lines=None):
    lines = [_marriage_status_line(marriage)]
    if marriage.get("children_status") == "no_children":
        lines.append("no children / کوئی اولاد نہیں")
    for extra in extra_lines or []:
        lines.append(extra)
    return mermaid_escape("<br/>".join(lines))


def _couple_parent_label(couple_key, children_by_couple, rels):
    children = children_by_couple.get(couple_key, [])
    if not children:
        return None
    child_set = set(children)
    kinds = {
        rel.get("kind")
        for rel in rels
        if rel["child"] in child_set and rel["parent"] in couple_key
    }
    if kinds == {"biological"}:
        return "biological parents / حقیقی والدین"
    return "parents / والدین"


def _relationship_label(group):
    """Bilingual wording for a direct secondary relationship edge."""
    return mermaid_escape(
        f"{group.get('label_en', '')} / {group.get('label_ur', '')}"
    )


def _semantic_render_specs(data):
    """Map every JSON relationship to its actual person-card endpoints."""
    (
        _,
        couples_in_order,
        _,
        children_by_couple,
        child_to_couple,
        couple_of_person,
        _,
        rels,
    ) = _couple_records(data)

    families = []
    for key, _ in couples_in_order:
        children = children_by_couple.get(key, [])
        if not children:
            continue
        families.append(
            {
                "id": _cluster_id(key),
                "cluster": _cluster_id(key),
                "junction": _junction_id(key),
                "parents": list(key),
                "children": [
                    {
                        "id": child,
                        "cluster": (
                            _cluster_id(couple_of_person[child])
                            if child in couple_of_person
                            else None
                        ),
                    }
                    for child in children
                ],
            }
        )

    parent_child = []
    for rel in rels:
        family_key = child_to_couple.get(rel["child"])
        parent_child.append(
            {
                "parent": rel["parent"],
                "child": rel["child"],
                "family": _cluster_id(family_key) if family_key else None,
                "mode": "junction" if family_key else "direct",
            }
        )

    marriages = [
        {
            "id": _cluster_id(_couple_key(marriage)),
            "people": list(_couple_key(marriage)),
        }
        for marriage in data["marriages"]
    ]
    sibling_groups = [
        {
            "id": group["id"],
            "members": list(group["members"]),
            "ordered": bool(group.get("ordered")),
        }
        for group in data.get("sibling_groups", [])
    ]
    return {
        "families": families,
        "parent_child": parent_child,
        "marriages": marriages,
        "sibling_groups": sibling_groups,
    }


def audit_render_mapping(data, mermaid_text):
    """Fail if any JSON relationship is absent from the render specification."""
    specs = _semantic_render_specs(data)
    expected_parent_child = {
        (rel["parent"], rel["child"]) for rel in data["parent_child"]
    }
    mapped_parent_child = {
        (rel["parent"], rel["child"]) for rel in specs["parent_child"]
    }
    if mapped_parent_child != expected_parent_child:
        raise ValueError("Parent-child render mapping does not match the structured data.")

    expected_marriages = {
        tuple(sorted((rel["person1"], rel["person2"])))
        for rel in data["marriages"]
    }
    mapped_marriages = {
        tuple(rel["people"]) for rel in specs["marriages"]
    }
    if mapped_marriages != expected_marriages:
        raise ValueError("Marriage render mapping does not match the structured data.")
    for first, second in expected_marriages:
        direct_edge = f"{_person_node_id(first)} ---|"
        direct_target = f"| {_person_node_id(second)}"
        if direct_edge not in mermaid_text or direct_target not in mermaid_text:
            raise ValueError(
                f"Marriage is not a direct person-to-person edge: {first}, {second}."
            )

    expected_groups = {
        group["id"]: (tuple(group["members"]), bool(group.get("ordered")))
        for group in data.get("sibling_groups", [])
    }
    mapped_groups = {
        group["id"]: (tuple(group["members"]), group["ordered"])
        for group in specs["sibling_groups"]
    }
    if mapped_groups != expected_groups:
        raise ValueError("Sibling-group render mapping does not match the structured data.")

    return {
        "parent_child": len(mapped_parent_child),
        "marriages": len(mapped_marriages),
        "sibling_groups": len(mapped_groups),
    }


# ---------------------------------------------------------------------------
# Derived kinship calculation (computed only, never written back to data)
# ---------------------------------------------------------------------------

VIRTUAL_FULL_ANCESTOR_PREFIX = "__full_shared_ancestor_"
MAX_KINSHIP_DEPTH = 30
ORDINAL_EN = {
    1: "first",
    2: "second",
    3: "third",
    4: "fourth",
    5: "fifth",
    6: "sixth",
    7: "seventh",
    8: "eighth",
    9: "ninth",
    10: "tenth",
}
COUSIN_UR_ZERO_REMOVAL = {
    1: "پہلے کزن",
    2: "دوسرے کزن",
    3: "تیسرے کزن",
}


def _biological_parent_index(data):
    """Biological parent-child graph only; derived kinship never uses
    non-biological links as blood ancestry."""
    parents = defaultdict(list)
    for rel in data.get("parent_child", []):
        if rel.get("kind") == "biological":
            parents[rel["child"]].append(rel["parent"])
    return parents


def _full_sibling_shared_ancestors(data, parents):
    """Full-sibling facts with unrecorded parents share one calculation-only
    virtual ancestor. The virtual id never appears in the diagram or in
    family.db and is never treated as a person.""" 
    for group in data.get("sibling_groups", []):
        if group.get("type") != "full":
            continue
        member_parent_sets = {
            tuple(sorted(parents.get(member, []))) for member in group["members"]
        }
        if member_parent_sets == {()}:
            virtual_id = f"{VIRTUAL_FULL_ANCESTOR_PREFIX}{group['id']}"
            for member in group["members"]:
                parents[member].append(virtual_id)


def _ancestor_chains(person_id, parents, cache, active=(), depth=0):
    """Every lineal chain from a person upward through biological parents,
    including calculation-only full-sibling ancestors."""
    if person_id in cache:
        return cache[person_id]
    if person_id in active or depth > MAX_KINSHIP_DEPTH:
        return []
    active = active + (person_id,)
    own_parents = parents.get(person_id, [])
    if not own_parents:
        chains = [(person_id,)]
    else:
        chains = []
        for parent in own_parents:
            for tail in _ancestor_chains(parent, parents, cache, active, depth + 1):
                chains.append((person_id,) + tail)
    cache[person_id] = chains
    return chains


def _side_of_parent_on_chain(parent_id, people_index):
    """'maternal' when the relationship path runs through the person's mother,
    'paternal' when it runs through the father."""
    if not people_index:
        return ""
    gender = people_index.get(parent_id, {}).get("gender")
    if gender == "female":
        return "maternal"
    if gender == "male":
        return "paternal"
    return ""


def _pair_path_records(data, first, second, people_index=None):
    """Every distinct lineage path between two people.

    Each pair of ancestor chains is counted once at its closest shared
    ancestor, so the same lineage is never double counted at higher
    ancestors, while genuinely different lineage pairs remain available as
    separate simultaneous relationship paths.
    """
    parents = _biological_parent_index(data)
    _full_sibling_shared_ancestors(data, parents)
    cache = {}
    first_chains = _ancestor_chains(first, parents, cache)
    second_chains = _ancestor_chains(second, parents, cache)
    found = {}

    def add(key, value):
        if key not in found:
            found[key] = value

    for chain_a in first_chains:
        set_a = set(chain_a)
        for chain_b in second_chains:
            set_b = set(chain_b)
            common = next((node for node in chain_a if node in set_b), None)
            if common is None:
                continue
            index_a = chain_a.index(common)
            index_b = chain_b.index(common)
            if index_a == 0 and index_b > 0:
                child_id = chain_b[index_b - 1] if index_b >= 1 else None
                add(
                    ("descendant", index_b),
                    {
                        "kind": "descendant",
                        "distance": index_b,
                        "child_id": child_id,
                    },
                )
                continue
            if index_b == 0 and index_a > 0:
                side = ""
                if index_a >= 2 and len(chain_a) > 1:
                    side = _side_of_parent_on_chain(chain_a[1], people_index)
                add(
                    ("ancestor", index_a, side),
                    {"kind": "ancestor", "distance": index_a, "side": side},
                )
                continue
            if index_a == 0 or index_b == 0:
                continue
            side = ""
            if len(chain_a) > 1:
                side = _side_of_parent_on_chain(chain_a[1], people_index)
            sibling_id = chain_b[1] if index_b >= 2 else None
            parent_first_id = chain_a[1] if index_a >= 2 else None
            key = (index_a, index_b, side, sibling_id, parent_first_id)
            add(
                key,
                {
                    "kind": "collateral",
                    "da": index_a,
                    "db": index_b,
                    "side": side,
                    "sibling_id": sibling_id,
                    "parent_first_id": parent_first_id,
                    "common_ancestor": common,
                },
            )
    return list(found.values())


def _kinship_terms(data, first, second, focus_id=None, people_index=None):
    """All distinct cousin-style terms between two people (computed wrapper
    over the shared path records; never written back to family data)."""
    if focus_id is not None and people_index is not None and second == focus_id and first != focus_id:
        records = _pair_path_records(data, second, first, people_index)
    else:
        records = _pair_path_records(data, first, second, people_index)
    found = {}
    for record in records:
        if record["kind"] != "collateral":
            continue
        da, db, side = record["da"], record["db"], record["side"]
        if da < 2 or db < 2:
            continue
        degree = min(da, db) - 1
        if degree < 1:
            continue
        removal = abs(da - db)
        key = (degree, removal, side)
        if key not in found:
            found[key] = {
                "degree": degree,
                "removal": removal,
                "side": side,
                "common_ancestor": record["common_ancestor"],
            }
    return sorted(
        found.values(),
        key=lambda term: (term["degree"], term["removal"], term["side"]),
    )


def _cousin_en(degree, removal, plural=False):
    noun = "cousins" if plural else "cousin"
    ordinal = ORDINAL_EN.get(degree)
    if ordinal is None:
        ordinal = f"{degree}th"
    base = f"{ordinal} {noun}"
    if removal == 1:
        return f"{base} once removed"
    if removal == 2:
        return f"{base} twice removed"
    if removal > 2:
        return f"{base} {removal} times removed"
    return base


def _cousin_ur(degree, removal):
    if removal == 0:
        return COUSIN_UR_ZERO_REMOVAL.get(degree)
    return None


def _derived_focus_entries(data):
    """Cousin-style relationship terms between the focus person and everyone
    else, with maternal/paternal side labels where the path is through one of
    the focus person's parents."""
    people_index = {person["id"]: person for person in data["people"]}
    focus_id = data["metadata"]["focus_person"]
    entries = []
    for person in data["people"]:
        person_id = person["id"]
        if person_id == focus_id:
            continue
        terms = _kinship_terms(
            data,
            focus_id,
            person_id,
            focus_id=focus_id,
            people_index=people_index,
        )
        if not terms:
            continue
        labels = []
        for term in terms:
            side = term["side"]
            prefix = f"{side} " if side in ("maternal", "paternal") else ""
            labels.append(prefix + _cousin_en(term["degree"], term["removal"]))
        entries.append({"id": person_id, "name": person["name"], "terms": labels})
    return entries


def _marriage_derived_lines(data, first, second):
    """Small bilingual annotations for a marriage whose spouses also have a
    derived cousin relationship (kept on the couple unit, not drawn as a
    second line over the marriage line)."""
    lines = []
    for term in _kinship_terms(data, first, second):
        en = _cousin_en(term["degree"], term["removal"], plural=True)
        ur = _cousin_ur(term["degree"], term["removal"])
        lines.append(f"{en} / {ur}" if ur else en)
    return lines


def _audit_derived(data):
    """Fail the build if any required derived consequence is not calculated."""
    people_index = {person["id"]: person for person in data["people"]}
    focus = data["metadata"]["focus_person"]
    problems = []

    def terms(person_id):
        return {
            (
                term["degree"],
                term["removal"],
                term["side"],
            )
            for term in _kinship_terms(
                data,
                focus,
                person_id,
                focus_id=focus,
                people_index=people_index,
            )
        }

    def require_subset(person_id, expected, label):
        actual = terms(person_id)
        missing = sorted(expected - actual)
        if missing:
            problems.append(f"{label} missing terms for {person_id}: {missing}.")

    pair = {
        (
            term["degree"],
            term["removal"],
            term["side"],
        )
        for term in _kinship_terms(data, "irsa_naz", "mansoor_hussain")
    }
    if (1, 0, "") not in pair:
        problems.append("Irsa Naz + Mansoor Hussain are not derived as first cousins.")

    for person_id in ("ezan_asif", "fakhir_asif"):
        require_subset(
            person_id,
            {(1, 0, "maternal"), (2, 0, "paternal")},
            "Ezan/Fakhir focus terms",
        )
    for person_id in (
        "aresha_zubair",
        "fizza_zubair",
        "abdul_rafey",
        "muaaz",
        "barirah",
        "musabiha",
        "musa",
    ):
        require_subset(
            person_id,
            {(1, 0, "paternal"), (2, 0, "maternal")},
            "Hina/Sana/Afshan child focus terms",
        )
    for person_id in ("aresha_owais_daughter_a", "aresha_owais_daughter_b"):
        require_subset(
            person_id,
            {(1, 1, "paternal"), (2, 1, "maternal")},
            "Aresha daughter focus terms",
        )
    if problems:
        raise ValueError("\n".join(f"- {problem}" for problem in problems))
    return {
        "focus_cousin_paths": len(_derived_focus_entries(data)),
    }


# ---------------------------------------------------------------------------
# Arbitrary-perspective relationship labels (used by the generated viewer)
# ---------------------------------------------------------------------------

GRAND_ANCESTOR_UR = {
    ("maternal", "male"): "نانا",
    ("maternal", "female"): "نانی",
    ("paternal", "male"): "دادا",
    ("paternal", "female"): "دادی",
}
UNCLE_AUNT_UR = {
    ("maternal", "male"): "ماموں",
    ("maternal", "female"): "خالہ",
    ("paternal", "male"): "چچا",
    ("paternal", "female"): "پھوپھی",
}


def _pair_relationship_entries(data, first, second, people_index):
    """All meaningful relationship terms from `first`'s perspective to
    `second`: explicit primary facts first, then every distinct derived path
    (direct blood roles and cousin paths)."""
    entries = []
    seen = set()

    def add(en, ur=None, group="primary"):
        key = (en, ur, group)
        if key in seen:
            return False
        seen.add(key)
        entries.append({"en": en, "ur": ur, "group": group})
        return True

    def gender_of(person_id):
        return people_index.get(person_id, {}).get("gender")

    # --- explicit primary facts --------------------------------------
    for marriage in data["marriages"]:
        if {marriage["person1"], marriage["person2"]} == {first, second}:
            if gender_of(second) == "female":
                add("Wife", "بیوی")
            else:
                add("Husband", "شوہر")

    child_gender_terms = {
        "male": ("Son", "بیٹا"),
        "female": ("Daughter", "بیٹی"),
    }
    for rel in data["parent_child"]:
        kind = rel.get("kind")
        suffix = f" ({kind})" if kind and kind != "biological" else ""
        if rel["parent"] == first and rel["child"] == second:
            term = child_gender_terms.get(gender_of(second), ("Child", "بچہ"))
            add(term[0] + suffix, term[1] if not suffix else None)
        if rel["parent"] == second and rel["child"] == first:
            role = rel.get("role")
            gender = gender_of(second)
            if role in ("mother", "father"):
                en = {"mother": "Mother", "father": "Father"}[role]
                ur = {"mother": "والدہ", "father": "والد"}[role]
            elif gender == "female":
                en, ur = "Mother", "والدہ"
            elif gender == "male":
                en, ur = "Father", "والد"
            else:
                en, ur = "Parent", "والدین"
            add(en + suffix, ur if not suffix else None)

    def same_biological_parents(a, b):
        parents_a = sorted(
            rel["parent"] for rel in data["parent_child"]
            if rel["child"] == a and rel.get("kind") == "biological"
        )
        parents_b = sorted(
            rel["parent"] for rel in data["parent_child"]
            if rel["child"] == b and rel.get("kind") == "biological"
        )
        return parents_a and parents_a == parents_b

    shared_groups = [
        group for group in data["sibling_groups"]
        if first in group["members"] and second in group["members"]
    ]
    sibling_added = False
    if shared_groups or same_biological_parents(first, second):
        explicit_full = any(group.get("type") == "full" for group in shared_groups)
        if gender_of(second) == "female":
            en = "Full sister" if explicit_full else "Sister"
            ur = "سگی بہن" if explicit_full else "بہن"
        else:
            en = "Full brother" if explicit_full else "Brother"
            ur = "سگا بھائی" if explicit_full else "بھائی"
        if add(en, ur):
            sibling_added = True

    # --- derived paths -------------------------------------------------
    records = _pair_path_records(data, first, second, people_index)
    for record in records:
        record_kind = record["kind"]
        if record_kind == "ancestor":
            distance = record["distance"]
            if distance == 1:
                continue
            side = record.get("side", "")
            target_gender = gender_of(second)
            if distance == 2:
                if target_gender == "male":
                    en = "Grandfather"
                else:
                    en = "Grandmother"
                if side == "maternal":
                    en = "Maternal " + en
                elif side == "paternal":
                    en = "Paternal " + en
                ur = GRAND_ANCESTOR_UR.get((side, target_gender))
                add(en, ur, "direct")
            else:
                prefix = "great-" * (distance - 2)
                base = "grandfather" if target_gender == "male" else "grandmother"
                add(f"{prefix}{base}", None, "direct")
        elif record_kind == "descendant":
            distance = record["distance"]
            if distance == 1:
                continue
            target_gender = gender_of(second)
            if distance == 2:
                en = "Grandson" if target_gender == "male" else "Granddaughter"
                child_id = record.get("child_id")
                child_gender = gender_of(child_id) if child_id else None
                if target_gender == "male":
                    ur = "پوتا" if child_gender == "male" else "نواسا"
                else:
                    ur = "پوتی" if child_gender == "male" else "نواسی"
                add(en, ur, "direct")
            else:
                prefix = "great-" * (distance - 2)
                base = "grandson" if target_gender == "male" else "granddaughter"
                add(f"{prefix}{base}", None, "direct")
        elif record_kind == "collateral":
            da, db, side = record["da"], record["db"], record["side"]
            if da == 1 and db == 1:
                if not sibling_added:
                    if gender_of(second) == "female":
                        add("Half sister", None, "direct")
                    else:
                        add("Half brother", None, "direct")
                    sibling_added = True
            elif da == 1 and db >= 2:
                depth = db - 1
                target_gender = gender_of(second)
                sibling_gender = gender_of(record.get("sibling_id"))
                if depth == 1:
                    en = "Niece" if target_gender == "female" else "Nephew"
                    if target_gender == "female":
                        ur = (
                            "بھانجی" if sibling_gender == "female" else "بھتیجی"
                            if sibling_gender == "male" else None
                        )
                    else:
                        ur = (
                            "بھانجا" if sibling_gender == "female" else "بھتیجا"
                            if sibling_gender == "male" else None
                        )
                    add(en, ur, "direct")
                else:
                    prefix = "grand" if depth == 2 else f"great-" * (depth - 2) + "grand"
                    base = "niece" if target_gender == "female" else "nephew"
                    add(f"{prefix}{base}", None, "direct")
            elif db == 1 and da >= 2:
                target_gender = gender_of(second)
                if da == 2:
                    en = "uncle" if target_gender == "male" else "aunt"
                    if side == "maternal":
                        en = "maternal " + en
                    elif side == "paternal":
                        en = "paternal " + en
                    en = en.capitalize()
                    ur = UNCLE_AUNT_UR.get((side, target_gender))
                    add(en, ur, "direct")
                else:
                    prefix = "great-" * (da - 2)
                    base = "uncle" if target_gender == "male" else "aunt"
                    if side == "maternal":
                        en = f"{prefix}maternal {base}".capitalize()
                    elif side == "paternal":
                        en = f"{prefix}paternal {base}".capitalize()
                    else:
                        en = f"{prefix}{base}".capitalize()
                    add(en, None, "direct")
            elif da >= 2 and db >= 2:
                degree = min(da, db) - 1
                if degree >= 1:
                    removal = abs(da - db)
                    side_text = f"{side} " if side in ("maternal", "paternal") else ""
                    en = side_text + _cousin_en(degree, removal)
                    ur = _cousin_ur(degree, removal)
                    add(en, ur, "cousin")
    return entries


def _viewer_pair(data, first, second, people_index):
    """Viewer entry for one ordered pair: primary/direct terms first, all
    remaining cousin paths preserved under additional."""
    if first == second:
        return {"main": [{"en": "Self", "ur": "خود"}], "additional": []}
    entries = _pair_relationship_entries(data, first, second, people_index)
    main = [
        {"en": entry["en"], "ur": entry["ur"]}
        for entry in entries if entry["group"] in ("primary", "direct")
    ]
    cousins = [
        {"en": entry["en"], "ur": entry["ur"]}
        for entry in entries if entry["group"] == "cousin"
    ]
    if not main:
        main = cousins
        cousins = []
    return {"main": main, "additional": cousins}


def _viewer_snapshot(data):
    """Objective graph + Python-computed relationship index embedded in the
    generated HTML. The browser never recalculates kinship itself, so there
    is exactly one canonical kinship implementation."""
    people_index = {person["id"]: person for person in data["people"]}
    relations = {}
    for first in data["people"]:
        row = {}
        for second in data["people"]:
            row[second["id"]] = _viewer_pair(
                data, first["id"], second["id"], people_index
            )
        relations[first["id"]] = row

    people_view = []
    for person in data["people"]:
        person_id = person["id"]
        parents = [
            {"id": rel["parent"], "role": rel["role"], "kind": rel["kind"]}
            for rel in data["parent_child"] if rel["child"] == person_id
        ]
        children = [
            rel["child"] for rel in data["parent_child"] if rel["parent"] == person_id
        ]
        spouses = [
            marriage["person2"] if marriage["person1"] == person_id
            else marriage["person1"]
            for marriage in data["marriages"]
            if person_id in (marriage["person1"], marriage["person2"])
        ]
        sibling_ids = []
        group_ids = []
        for group in data["sibling_groups"]:
            if person_id in group["members"]:
                group_ids.append(group["id"])
                sibling_ids.extend(
                    member for member in group["members"] if member != person_id
                )
        people_view.append(
            {
                "id": person_id,
                "name": person["name"],
                "aliases": person.get("aliases", []),
                "birth_year": person.get("birth_year"),
                "gender": person.get("gender"),
                "marital_status": person.get("marital_status"),
                "notes": (
                    {"en": person["note_en"], "ur": person.get("note_ur")}
                    if person.get("note_en")
                    else None
                ),
                "photo_path": person.get("photo_path"),
                "parents": parents,
                "children": children,
                "spouses": spouses,
                "siblings": sorted(set(sibling_ids)),
                "sibling_groups": group_ids,
            }
        )
    return {
        "app": {
            "title": data["metadata"].get("title", "Family Relationships / خاندانی رشتے"),
            "revision": data["metadata"].get("revision"),
            "updated": data["metadata"].get("updated"),
            "focus_id": data["metadata"].get("focus_person"),
            "source_batches": data["metadata"].get("source_batches", []),
            "source_of_truth": "family.db",
        },
        "people": people_view,
        "relations": relations,
    }


def _kinship_regression_audit(data):
    """Phase-2 regression checks for arbitrary perspectives; fails the build
    if any required relationship is missing."""
    people_index = {person["id"]: person for person in data["people"]}

    def entry_labels(first, second):
        pair = _viewer_pair(data, first, second, people_index)
        return {
            label["en"]
            for label in pair["main"] + pair["additional"]
        }

    problems = []

    def require(first, second, expected, label):
        actual = entry_labels(first, second)
        missing = [
            phrase
            for phrase in expected
            if not any(phrase in item for item in actual)
        ]
        if missing:
            problems.append(f"{label}: missing {missing} for {first} -> {second}.")

    require("mohammad_yahya_hussain", "maham_mansoor", {"Sister"}, "direct sibling")
    require("mohammad_yahya_hussain", "ezan_asif",
            {"maternal first cousin", "paternal second cousin"}, "Ezan paths")
    require("mohammad_yahya_hussain", "aresha_zubair",
            {"paternal first cousin", "maternal second cousin"}, "Aresha paths")
    require("irsa_naz", "mansoor_hussain", {"Husband"}, "Irsa spouse")
    require("mohammad_yahya_hussain", "mohammad_yahya_hussain", {"Self"}, "self")
    require("mansoor_hussain", "aresha_zubair", {"Niece"}, "Mansoor niece")
    require("irsa_naz", "aresha_zubair", {"first cousin once removed"}, "Irsa to Aresha")
    require("irsa_naz", "ezan_asif", {"Nephew"}, "Irsa nephew")
    require("ezan_asif", "irsa_naz", {"aunt"}, "Ezan aunt")
    if problems:
        raise ValueError("\n".join(f"- {problem}" for problem in problems))
    return len(people_index)


def build_mermaid(data):
    """Return ONE Mermaid diagram string generated from family.db."""
    (
        people_index,
        couples_in_order,
        marriages_by_key,
        children_by_couple,
        child_to_couple,
        couple_of_person,
        parents_of,
        rels,
    ) = _couple_records(data)
    depths = _person_depths(data, parents_of)
    markers = _order_markers(data)
    focus = data["metadata"]["focus_person"]
    relationship_groups = [
        group for group in data.get("sibling_groups", []) if not group.get("ordered")
    ]

    side_cache = {}
    branch_by_couple = {}
    palette_by_couple = {}
    for key, _ in couples_in_order:
        branch = _couple_visual_branch(key, people_index, parents_of, side_cache)
        branch_by_couple[key] = branch
        if branch == MATERNAL:
            palette_by_couple[key] = MATERNAL_PALETTE
        elif branch == PATERNAL:
            palette_by_couple[key] = PATERNAL_PALETTE

    ordered_couples = _couple_sort_keys(
        couples_in_order, depths, markers, branch_by_couple
    )

    # Deterministic palette slot per branch (marriage-list order per branch).
    style_index = {}
    counters = {MATERNAL: 0, PATERNAL: 0}
    for key, _ in couples_in_order:
        branch = branch_by_couple[key]
        if branch in counters:
            style_index[key] = counters[branch]
            counters[branch] += 1

    lines = [
        "flowchart TB",
        "  %% Generated from family.db by build_family.py. Source of truth: family.db.",
        "  %% Current master layout: maternal left, bridge center, paternal right.",
        "  %% Couple clusters are colored visual units only. Junctions (j_*) are",
        "  %% layout-only helpers: not people and never written back to family.db.",
        "  classDef person fill:#ffffff,stroke:#6b7280,color:#111111;",
        "  classDef matperson fill:#FFE9EF,stroke:#DBA3B4,color:#111111;",
        "  classDef patperson fill:#E1EEFF,stroke:#97B6DE,color:#111111;",
        "  classDef focus stroke:#c62828,stroke-width:3px,color:#111111;",
        "  classDef junc fill:none,stroke:none,color:none;",
        "  classDef route fill:none,stroke:none,color:none;",
    ]

    # Invisible routing-only helpers reserve separate relationship lanes while
    # keeping external links attached to whole couple clusters. This preserves
    # the compact LR spouse layout in Mermaid 11.4.1. The HTML renderer extends
    # those paths to the actual person cards after Mermaid finishes.
    top_rel_groups = []
    below_rel_groups = []

    def visual_row_depth(person_id):
        couple_key = couple_of_person.get(person_id)
        if couple_key:
            return max(depths[spouse] for spouse in couple_key)
        return depths.get(person_id, 0)

    for group in relationship_groups:
        members = group.get("members", [])
        if members and max(visual_row_depth(member) for member in members) == 0:
            top_rel_groups.append(group)
        else:
            below_rel_groups.append(group)

    for group in top_rel_groups:
        lines.append(f'    {_route_node_id(group["id"])}[" "]')

    declared_people = set()

    def declare_person(person_id):
        if person_id in declared_people:
            return
        declared_people.add(person_id)
        person = people_index[person_id]
        lines.append(
            f'    {_person_node_id(person_id)}["{_person_label(person, markers.get(person_id))}"]'
        )

    # --- Couple units: one compact LR cluster per marriage. Marriage is a
    # direct edge between the two spouse cards; no caption node sits between.
    for key, marriage in ordered_couples:
        first, second = key
        lines.append(f'  subgraph {_cluster_id(key)}[" "]')
        lines.append("    direction LR")
        for spouse in (first, second):
            declare_person(spouse)
        derived_lines = _marriage_derived_lines(data, first, second)
        lines.append(
            f'    {_person_node_id(first)} ---|"{_marriage_label(marriage, derived_lines)}"| '
            f'{_person_node_id(second)}'
        )
        lines.append("  end")

    # --- Layout-only family junctions for couples that have recorded children.
    junction_keys = [
        key for key, _ in ordered_couples if children_by_couple.get(key)
    ]
    for key in junction_keys:
        lines.append(f'    {_junction_id(key)}[" "]')

    for group in below_rel_groups:
        lines.append(f'    {_route_node_id(group["id"])}[" "]')

    # --- Children and every remaining person are plain nodes.
    for key, _ in ordered_couples:
        for child in children_by_couple.get(key, []):
            declare_person(child)
    for person in data["people"]:
        declare_person(person["id"])

    lines.append("")

    # --- REAL FAMILY EDGES ------------------------------------------------
    # Couple cluster -> family junction (vertical parent relationship), then
    # junction -> each child. A married child is reached through that child's
    # own couple cluster so individual spouse cards stay side by side.
    real_edges = []

    def keep_secondary_linked_children_adjacent(children):
        """Nudge linked child-couples together without changing family facts.

        The numbered markers remain the authoritative birth order. This only
        changes Mermaid declaration order so a secondary relationship can use
        a short, unobstructed lane between nearby couple units.
        """
        arranged = list(children)
        child_set = set(arranged)

        def child_married_to(member):
            key = couple_of_person.get(member)
            if not key:
                return member if member in child_set else None
            partner = key[0] if key[1] == member else key[1]
            return partner if partner in child_set else None

        for group in relationship_groups:
            members = group.get("members", [])
            if len(members) != 2:
                continue
            first = child_married_to(members[0])
            second = child_married_to(members[1])
            if not first or not second or first == second:
                continue
            arranged.remove(second)
            arranged.insert(arranged.index(first) + 1, second)
        return arranged

    for key in junction_keys:
        parent_label = _couple_parent_label(key, children_by_couple, rels)
        real_edges.append(
            f'    {_cluster_id(key)} -->|"{mermaid_escape(parent_label)}"| '
            f'{_junction_id(key)}'
        )
        # Current-master layout preference only: keep the bridge child nearest
        # the center. Maternal siblings fan toward it from the left; paternal
        # siblings fan away from it to the right. Birth order remains recorded
        # by the visible [n] markers and is not changed as a family fact.
        children = list(children_by_couple[key])
        couple_depth = max(depths[spouse] for spouse in key)
        children = keep_secondary_linked_children_adjacent(children)
        if couple_depth == 0:
            root_branch = branch_by_couple[key]

            def is_bridge_child(child):
                child_couple = couple_of_person.get(child)
                return (
                    child_couple is not None
                    and branch_by_couple[child_couple] == BRIDGE
                )

            children.sort(
                key=is_bridge_child,
                reverse=(root_branch == PATERNAL),
            )
        for child in children:
            target = (
                _cluster_id(couple_of_person[child])
                if child in couple_of_person
                else _person_node_id(child)
            )
            real_edges.append(f"    {_junction_id(key)} --> {target}")

    # --- LAYOUT-ONLY HELPERS / PIN EDGES ---------------------------------
    # None are needed: Mermaid ranks whole couple clusters, so no hidden
    # ancestry-to-spouse pin edges are generated at all.

    # --- Secondary recorded relationships --------------------------------
    # Neutral dotted relationship paths use invisible lane helpers. Married
    # members attach to the couple boundary here so Mermaid keeps spouses in a
    # compact LR unit; family.html extends the same path to the real person card.
    # Unmarried members already attach directly to their real person card.
    secondary_edges = []
    for group in top_rel_groups + below_rel_groups:
        helper = _route_node_id(group["id"])
        label = _relationship_label(group)
        members = list(group.get("members", []))
        if group in top_rel_groups:
            # Current master view only: let the top relationship lane reinforce
            # maternal-left / paternal-right instead of reversing both roots.
            members.sort(
                key=lambda member: (
                    PATERNAL
                    in _person_side(
                        member, people_index, parents_of, side_cache
                    ),
                    member,
                )
            )
        for index, member in enumerate(members):
            endpoint = (
                _cluster_id(couple_of_person[member])
                if member in couple_of_person
                else _person_node_id(member)
            )
            link = f'-. "{label}" .-' if index == 0 else "-.-"
            if group in top_rel_groups:
                secondary_edges.append(f"    {helper} {link} {endpoint}")
            else:
                secondary_edges.append(f"    {endpoint} {link} {helper}")

    # --- Fallback direct parent-child edges for facts outside any married
    # couple (safety path; none exist in the current data).
    direct_edges = []
    for rel in rels:
        if rel["child"] not in child_to_couple:
            direct_edges.append(
                f'    {_person_node_id(rel["parent"])} --> '
                f'{_person_node_id(rel["child"])}'
            )

    for edge in real_edges + secondary_edges + direct_edges:
        lines.append(edge)

    lines.append("")

    # --- Styles and classes.
    bridge_persons = set()
    for key, _ in ordered_couples:
        if branch_by_couple[key] == BRIDGE:
            bridge_persons.update(key)

    # One class per statement keeps the generated syntax compatible across
    # Mermaid renderers. Person cards are white; bridge cards get their own
    # pale pink / pale blue class instead of the white person class.
    lines.append(f"    class {_person_node_id(focus)} person;")
    lines.append(f"    class {_person_node_id(focus)} focus;")
    for person in data["people"]:
        person_id = person["id"]
        if person_id != focus and person_id not in bridge_persons:
            lines.append(f"    class {_person_node_id(person_id)} person;")

    for key, _ in ordered_couples:
        cluster = _cluster_id(key)
        branch = branch_by_couple[key]
        if branch == BRIDGE:
            # Irsa (maternal) + Mansoor (paternal): neutral shared boundary,
            # one pale-pink card and one pale-blue card.
            fill, stroke = NEUTRAL_COUPLE
            for spouse in key:
                spouse_side = _person_side(
                    spouse, people_index, parents_of, side_cache
                )
                if spouse_side == {MATERNAL}:
                    lines.append(f"    class {_person_node_id(spouse)} matperson;")
                elif spouse_side == {PATERNAL}:
                    lines.append(f"    class {_person_node_id(spouse)} patperson;")
        else:
            palette = palette_by_couple.get(key)
            if palette is None:
                fill, stroke = ("#F7F7F9", "#B5B5C0")
            else:
                index = style_index.get(key, 0)
                fill, stroke = palette[index % len(palette)]
        lines.append(
            f"    style {cluster} fill:{fill},stroke:{stroke},color:#111111;"
        )

    for key in junction_keys:
        lines.append(f"    class {_junction_id(key)} junc;")
    for group in relationship_groups:
        lines.append(f"    class {_route_node_id(group['id'])} route;")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Markdown and HTML rendering (one shared Mermaid string)
# ---------------------------------------------------------------------------


def _revision_line(data):
    return f"Revision {data['metadata']['revision']} — {data['metadata']['updated']}"


def _derived_focus_section(data):
    """Markdown for the calculated focus-person cousin relationships."""
    entries = _derived_focus_entries(data)
    if not entries:
        return ""
    people_index = {person["id"]: person for person in data["people"]}
    focus_id = data["metadata"]["focus_person"]
    focus_name = people_index[focus_id]["name"]
    lines = [
        "## Derived cousin relationships / اخذ کردہ کزن رشتے",
        "",
        "Calculated from the biological parent-child graph and full-sibling "
        "facts in family.db; these are not stored as user-stated facts.",
        "",
        "Side labels (maternal / paternal) show which of the focus person's "
        "parents the path runs through. Simple terms: first cousin / پہلے کزن، "
        "second cousin / دوسرے کزن.",
        "",
        f"### For {focus_name} (focus) / مرکزی شخص کے لیے",
        "",
    ]
    for entry in entries:
        lines.append(f"- **{entry['name']}** — " + "; ".join(entry["terms"]))
    lines.append("")
    return "\n".join(lines)


def _derived_focus_section_html(data):
    """HTML for the same calculated focus-person cousin relationships."""
    entries = _derived_focus_entries(data)
    if not entries:
        return ""
    people_index = {person["id"]: person for person in data["people"]}
    focus_id = data["metadata"]["focus_person"]
    focus_name = people_index[focus_id]["name"]
    parts = [
        "<h2>Derived cousin relationships / اخذ کردہ کزن رشتے</h2>",
        "<p>Calculated from the biological parent-child graph and full-sibling "
        "facts in <code>family.db</code>; these are not stored as user-stated "
        "facts. Side labels (maternal / paternal) show which of the focus "
        "person's parents the path runs through. Simple terms: "
        "first cousin / پہلے کزن، second cousin / دوسرے کزن.</p>",
        f"<h3>For {html_module.escape(focus_name)} (focus) / مرکزی شخص کے لیے</h3>",
        '<ul class="detail-list">',
    ]
    for entry in entries:
        escaped_name = html_module.escape(entry["name"])
        parts.append(
            f"<li><strong>{escaped_name}</strong> — "
            f"{html_module.escape('; '.join(entry['terms']))}</li>"
        )
    parts.append("</ul>")
    return "\n".join(parts)


def _placeholder_sections(data):
    sections = []

    open_notes = [
        note for note in data.get("review_notes", []) if note.get("status") == "open"
    ]
    lines = ["## Open review notes / زیرِ جائزہ نکات", ""]
    if open_notes:
        for note in open_notes:
            lines.append(f"- **{note['id']}** — {note['text']}")
    else:
        lines.append("- None / کوئی نہیں")
    sections.append("\n".join(lines))

    deferred_notes = [
        note
        for note in data.get("review_notes", [])
        if note.get("status") == "deferred"
    ]
    lines = ["## Deferred / on-hold items / زیرِ التوا", ""]
    if deferred_notes:
        for note in deferred_notes:
            lines.append(f"- **{note['id']}** — {note['text']}")
    else:
        lines.append("- None / کوئی نہیں")
    sections.append("\n".join(lines))

    placeholder_notes = [
        note
        for note in data.get("review_notes", [])
        if note.get("status") == "placeholder"
    ]
    lines = ["## Preserved placeholders / محفوظ نامکمل معلومات", ""]
    for note in placeholder_notes:
        lines.append(f"- **{note['id']}** — {note['text']}")
    sections.append("\n".join(lines))

    lines = [
        "## Validation summary",
        "",
        f"- People: {len(data['people'])}",
        f"- Parent-child facts: {len(data['parent_child'])}",
        f"- Marriages: {len(data['marriages'])}",
        f"- Sibling groups: {len(data['sibling_groups'])}",
        "- Duplicate IDs, missing references, duplicate edges, and ancestry cycles: checked",
        "- Parent kinds, marital status, marriage children_status, sibling-group types, and no-children conflicts: checked",
        "- Derived cousin relationships: calculated from the explicit graph and audited at build time",
    ]
    sections.append("\n".join(lines))
    return sections


READING_GUIDE = [
    "Each married couple is one compact horizontal unit: spouses sit beside each other and the horizontal line between them is the marriage, with the recorded year where known.",
    "Parent lines leave both actual parent cards, meet at a separate family junction, and fan out to the actual child cards; `parents / والدین` or `biological parents / حقیقی والدین` is written on the shared downward line.",
    "A couple without recorded children has no child junction; `no children / کوئی اولاد نہیں` stays on the marriage line where recorded.",
    "In this current master view, maternal-side pink units occupy the left and paternal-side blue units occupy the right. Irsa Naz + Mansoor Hussain remain the central bridge, using one pink card and one blue card inside a neutral boundary.",
    "`[1]`, `[2]`, ... before a name record birth order within that sibling group.",
    "Direct neutral dotted lines connect the existing person cards for other recorded sibling/cross-family relationships; the relationship wording appears on the line and person names are not repeated.",
    "Derived cousin relationships (first/second cousin and once-removed terms with maternal/paternal sides) are calculated from biological links and full-sibling facts; they appear in the generated derived-relationships section, and a couple that is also a cousin pair gets a small annotation on its marriage line.",
]


def render_markdown(data, mermaid_text):
    lines = [
        "# Family Relationships / خاندانی رشتے",
        "",
        _revision_line(data),
        "",
        "> Generated from `family.db`. Update the data file, then run `python3.11 build_family.py`.",
        "> `family.md` and `family.html` are generated together from the same Mermaid diagram string.",
        ">",
        "> Reading guide:",
    ]
    for item in READING_GUIDE:
        lines.append(f"> - {item}")
    lines += [
        "",
        "```mermaid",
        mermaid_text,
        "```",
        "",
    ]
    derived_section = _derived_focus_section(data)
    if derived_section:
        lines.append(derived_section)
    for section in _placeholder_sections(data):
        lines.append(section)
        lines.append("")
    return "\n".join(lines)


_VIEWER_CSS = """
  .app-shell { display: flex; align-items: flex-start; gap: 18px; margin: 0 24px 20px 24px; }
  .main-col { flex: 1 1 auto; min-width: 0; }
  .main-col .diagram { margin: 14px 0 0 0; }
  .app-toolbar {
    display: flex; flex-wrap: wrap; gap: 8px 18px; align-items: center;
    padding: 10px 14px; border: 1px solid #e0e0e0; border-radius: 8px;
    background: #fbfbfd;
  }
  .toolbar-search { position: relative; }
  #person-search { width: 240px; padding: 7px 10px; border: 1px solid #c8c8d2; border-radius: 6px; font-size: 14px; }
  .search-results {
    position: absolute; z-index: 40; top: 34px; left: 0; min-width: 260px;
    max-height: 240px; overflow: auto; background: #ffffff; border: 1px solid #d0d0da;
    border-radius: 6px; box-shadow: 0 4px 12px rgba(0,0,0,0.12); display: none;
  }
  .search-results .result-row { padding: 7px 10px; cursor: pointer; font-size: 14px; }
  .search-results .result-row:hover { background: #eef4ff; }
  .toolbar-state { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; font-size: 14px; }
  .toolbar-state button {
    padding: 6px 12px; border: 1px solid #a9b8d0; border-radius: 6px;
    background: #ffffff; cursor: pointer; font-size: 13px;
  }
  .toolbar-state button:hover { background: #eef4ff; }
  .side-panel {
    flex: 0 0 340px; width: 340px; max-height: 92vh; overflow: auto;
    position: sticky; top: 12px; border: 1px solid #e0e0e0; border-radius: 10px;
    background: #ffffff; padding: 14px 16px; font-size: 14px;
  }
  .panel-photo { min-height: 74px; display: flex; align-items: center; gap: 12px; }
  .panel-photo img { width: 72px; height: 72px; object-fit: cover; border-radius: 8px; border: 1px solid #e0e0e0; }
  .photo-initials {
    width: 72px; height: 72px; border-radius: 8px; background: #e9ecf3;
    color: #47526b; display: flex; align-items: center; justify-content: center;
    font-size: 28px; border: 1px solid #dfe3ec;
  }
  .panel-name { margin: 2px 0 4px 0; font-size: 19px; }
  .panel-aliases { color: #666; font-size: 13px; margin-bottom: 6px; }
  .panel-facts, .panel-family { margin: 6px 0; line-height: 1.45; }
  .fact-label { color: #555; }
  .rel-list { margin: 4px 0 8px 0; }
  .rel-item { padding: 3px 0; }
  .rel-ur { color: #005; direction: rtl; unicode-bidi: embed; margin-left: 6px; }
  .rel-note { color: #777; font-size: 13px; margin: 2px 0 6px 0; }
  .panel-box { margin-top: 10px; border-top: 1px solid #ececf2; padding-top: 8px; }
  .panel-box summary { cursor: pointer; color: #333; font-weight: 600; }
  .compare-row { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; }
  .compare-row select { padding: 6px; border-radius: 6px; border: 1px solid #c8c8d2; }
  .compare-row button { padding: 7px 12px; border-radius: 6px; border: 1px solid #a9b8d0; background: #ffffff; cursor: pointer; }
  .compare-row button:hover { background: #eef4ff; }
  #compare-out { margin-top: 8px; }
  #compare-out h4 { margin: 10px 0 4px 0; font-size: 14px; }
  .viewer-ring { fill: none; stroke: #d84315; stroke-width: 5; pointer-events: none; }
  g.node { cursor: pointer; }
"""


_VIEWER_JS = """
(() => {
  const dataElement = document.getElementById("family-data");
  if (!dataElement) return;
  const FAMILY = JSON.parse(dataElement.textContent);
  const byId = {};
  FAMILY.people.forEach((person) => { byId[person.id] = person; });
  const state = {
    perspective: FAMILY.app.focus_id,
    selected: FAMILY.app.focus_id,
  };
  const $ = (id) => document.getElementById(id);

  function waitForRender(callback) {
    if (window.familyRenderReady) {
      callback();
      return;
    }
    setTimeout(() => waitForRender(callback), 120);
  }

  function nodeFor(personId) {
    return document.querySelector('[id^="flowchart-p_' + personId + '-"]');
  }

  function relItems(containerId, list, emptyText) {
    const container = $(containerId);
    container.innerHTML = "";
    if (!list || !list.length) {
      if (emptyText) {
        const note = document.createElement("div");
        note.className = "rel-note";
        note.textContent = emptyText;
        container.appendChild(note);
      }
      return;
    }
    list.forEach((item) => {
      const row = document.createElement("div");
      row.className = "rel-item";
      const en = document.createElement("span");
      en.className = "rel-en";
      en.textContent = item.en;
      row.appendChild(en);
      if (item.ur) {
        const ur = document.createElement("span");
        ur.className = "rel-ur";
        ur.textContent = item.ur;
        row.appendChild(ur);
      }
      container.appendChild(row);
    });
  }

  function clearRing() {
    const old = document.querySelector("rect.viewer-ring");
    if (old) old.remove();
  }

  function ringFor(personId) {
    clearRing();
    const node = nodeFor(personId);
    if (!node) return;
    const card = node.querySelector(":scope > rect");
    if (!card) return;
    const ring = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    ring.setAttribute("class", "viewer-ring");
    ring.setAttribute("x", card.getAttribute("x"));
    ring.setAttribute("y", card.getAttribute("y"));
    ring.setAttribute("width", card.getAttribute("width"));
    ring.setAttribute("height", card.getAttribute("height"));
    node.appendChild(ring);
  }

  function personName(personId) {
    const person = byId[personId];
    return person ? person.name : personId;
  }

  function selectPerson(personId, focusCard) {
    state.selected = personId;
    ringFor(personId);
    const node = nodeFor(personId);
    if (focusCard && node) {
      try { node.scrollIntoView({ block: "center", inline: "center", behavior: "smooth" }); }
      catch (error) { node.scrollIntoView(); }
    }
    renderSidePanel();
  }

  function roleLabel(role) {
    return {
      mother: "Mother",
      father: "Father",
      parent: "Parent",
      unknown: "Parent",
    }[role] || "Parent";
  }

  function namesOf(ids) {
    return ids.map(personName).join(", ") || "—";
  }

  function factsHtml(person) {
    const facts = [];
    if (person.birth_year) facts.push(["Born", String(person.birth_year)]);
    const genderText = { male: "Male / مرد", female: "Female / عورت", unknown: "Unknown / نامعلوم" }[person.gender] || "";
    if (genderText) facts.push(["Gender", genderText]);
    if (person.marital_status === "single") facts.push(["Marital status", "Single / غیر شادی شدہ"]);
    const labels = document.createElement("div");
    facts.forEach(([label, value]) => {
      const line = document.createElement("div");
      line.className = "panel-facts";
      const span = document.createElement("span");
      span.className = "fact-label";
      span.textContent = label + ": ";
      line.appendChild(span);
      line.appendChild(document.createTextNode(value));
      labels.appendChild(line);
    });
    return labels;
  }

  function familyHtml(person) {
    const box = document.createElement("div");
    const addLine = (label, text) => {
      const line = document.createElement("div");
      line.className = "panel-family";
      const span = document.createElement("span");
      span.className = "fact-label";
      span.textContent = label + ": ";
      line.appendChild(span);
      line.appendChild(document.createTextNode(text));
      box.appendChild(line);
    };
    if (person.parents.length) {
      const parts = person.parents.map((rel) => {
        const name = personName(rel.id);
        const kind = rel.kind && rel.kind !== "biological" ? " (" + rel.kind + ")" : "";
        return name + " (" + roleLabel(rel.role) + kind + ")";
      });
      addLine("Parents", parts.join(", "));
    }
    if (person.spouses.length) addLine("Spouse(s)", namesOf(person.spouses));
    if (person.children.length) addLine("Children", namesOf(person.children));
    if (person.siblings.length) addLine("Siblings", namesOf(person.siblings));
    if (person.notes && person.notes.en) {
      addLine("Note", person.notes.en);
    }
    return box;
  }

  function photoHtml(person) {
    const holder = $("panel-photo");
    holder.innerHTML = "";
    const initials = document.createElement("div");
    initials.className = "photo-initials";
    const words = person.name.split(/\\s+/).filter(Boolean);
    initials.textContent = words.length > 1
      ? (words[0][0] + words[words.length - 1][0]).toUpperCase()
      : person.name.slice(0, 2).toUpperCase();
    if (!person.photo_path) {
      holder.appendChild(initials);
      return;
    }
    const image = document.createElement("img");
    image.alt = person.name;
    image.src = person.photo_path;
    image.onerror = () => {
      image.remove();
      holder.appendChild(initials);
    };
    holder.appendChild(image);
  }

  function renderSidePanel() {
    const person = byId[state.selected];
    if (!person) return;
    photoHtml(person);
    $("panel-name").textContent = person.name;
    const aliases = person.aliases && person.aliases.length ? "Alias: " + person.aliases.join(" / ") : "";
    $("panel-aliases").textContent = aliases;
    const facts = factsHtml(person);
    const family = familyHtml(person);
    $("panel-facts").innerHTML = "";
    $("panel-facts").appendChild(facts);
    $("panel-family").innerHTML = "";
    $("panel-family").appendChild(family);

    $("panel-rel-heading").textContent =
      "Relationship to " + personName(state.perspective) +
      " / " + personName(state.perspective) + " کے لحاظ سے رشتہ";
    const pair = FAMILY.relations[state.perspective][state.selected];
    const main = pair.main || [];
    const additional = pair.additional || [];
    relItems("panel-rel-main", main, "No recorded relationship / کوئی ریکارڈ شدہ رشتہ نہیں");
    const additionalBox = $("panel-rel-additional");
    additionalBox.innerHTML = "";
    if (additional.length) {
      const heading = document.createElement("div");
      heading.className = "fact-label";
      heading.textContent = "Additional derived relationship paths / اضافی اخذ کردہ رشتے";
      additionalBox.appendChild(heading);
      const listWrap = document.createElement("div");
      listWrap.className = "rel-list";
      additional.forEach((item) => {
        const row = document.createElement("div");
        row.className = "rel-item";
        row.textContent = item.en;
        if (item.ur) {
          const ur = document.createElement("span");
          ur.className = "rel-ur";
          ur.textContent = item.ur;
          row.appendChild(ur);
        }
        listWrap.appendChild(row);
      });
      additionalBox.appendChild(listWrap);
    }
    renderAllRelationships();
    fillCompareSelects();
  }

  function renderAllRelationships() {
    const list = $("perspective-all-list");
    list.innerHTML = "";
    FAMILY.people.forEach((person) => {
      const row = document.createElement("div");
      row.className = "rel-item";
      const name = document.createElement("span");
      name.className = "rel-en";
      name.textContent = person.name + ": ";
      row.appendChild(name);
      const pair = FAMILY.relations[state.perspective][person.id];
      const labels = (pair.main || []).map((item) => item.en);
      const ur = (pair.main || []).filter((item) => item.ur).map((item) => item.ur);
      const text = document.createElement("span");
      text.textContent = labels.join("; ");
      row.appendChild(text);
      if (ur.length) {
        const urText = document.createElement("span");
        urText.className = "rel-ur";
        urText.textContent = ur.join("، ");
        row.appendChild(urText);
      }
      if ((pair.additional || []).length) {
        const extra = document.createElement("div");
        extra.className = "rel-note";
        extra.textContent = "Additional: " + pair.additional.map((item) => item.en).join("; ");
        row.appendChild(extra);
      }
      list.appendChild(row);
    });
  }

  function fillCompareSelects() {
    const a = $("compare-a");
    const b = $("compare-b");
    a.innerHTML = "";
    b.innerHTML = "";
    FAMILY.people.forEach((person) => {
      [a, b].forEach((select) => {
        const option = document.createElement("option");
        option.value = person.id;
        option.textContent = person.name;
        select.appendChild(option);
      });
    });
    a.value = state.perspective;
    b.value = state.selected;
  }

  function showCompare() {
    const a = $("compare-a").value;
    const b = $("compare-b").value;
    const out = $("compare-out");
    out.innerHTML = "";
    const headingA = document.createElement("h4");
    headingA.textContent = "How is " + personName(b) + " related to " + personName(a) + "?";
    out.appendChild(headingA);
    const pairA = FAMILY.relations[a][b];
    const boxA = document.createElement("div");
    boxA.className = "rel-list";
    (pairA.main || []).concat(pairA.additional || []).forEach((item) => {
      const line = document.createElement("div");
      line.className = "rel-item";
      line.textContent = item.en;
      if (item.ur) {
        const ur = document.createElement("span");
        ur.className = "rel-ur";
        ur.textContent = item.ur;
        line.appendChild(ur);
      }
      boxA.appendChild(line);
    });
    if (!boxA.childNodes.length) {
      const none = document.createElement("div");
      none.className = "rel-note";
      none.textContent = "No recorded relationship / کوئی ریکارڈ شدہ رشتہ نہیں";
      boxA.appendChild(none);
    }
    out.appendChild(boxA);

    const headingB = document.createElement("h4");
    headingB.textContent = "How is " + personName(a) + " related to " + personName(b) + "?";
    out.appendChild(headingB);
    const pairB = FAMILY.relations[b][a];
    const boxB = document.createElement("div");
    boxB.className = "rel-list";
    (pairB.main || []).concat(pairB.additional || []).forEach((item) => {
      const line = document.createElement("div");
      line.className = "rel-item";
      line.textContent = item.en;
      if (item.ur) {
        const ur = document.createElement("span");
        ur.className = "rel-ur";
        ur.textContent = item.ur;
        line.appendChild(ur);
      }
      boxB.appendChild(line);
    });
    if (!boxB.childNodes.length) {
      const none = document.createElement("div");
      none.className = "rel-note";
      none.textContent = "No recorded relationship / کوئی ریکارڈ شدہ رشتہ نہیں";
      boxB.appendChild(none);
    }
    out.appendChild(boxB);
  }

  function setPerspective(personId) {
    state.perspective = personId;
    $("perspective-name").textContent = personName(personId);
    $("panel-rel-heading").textContent =
      "Relationship to " + personName(state.perspective) +
      " / " + personName(state.perspective) + " کے لحاظ سے رشتہ";
    renderSidePanel();
  }

  function setupSearch() {
    const input = $("person-search");
    const results = $("search-results");
    input.addEventListener("input", () => {
      const query = input.value.trim().toLowerCase();
      results.innerHTML = "";
      if (!query) {
        results.style.display = "none";
        return;
      }
      const matches = FAMILY.people.filter((person) => {
        const haystack = [person.name]
          .concat(person.aliases || [])
          .join(" ").toLowerCase();
        return haystack.indexOf(query) !== -1;
      }).slice(0, 12);
      matches.forEach((person) => {
        const row = document.createElement("div");
        row.className = "result-row";
        row.textContent = person.name;
        row.addEventListener("mousedown", (event) => {
          event.preventDefault();
          selectPerson(person.id, true);
          results.style.display = "none";
          input.value = person.name;
        });
        results.appendChild(row);
      });
      results.style.display = matches.length ? "block" : "none";
    });
    document.addEventListener("click", (event) => {
      if (!event.target.closest(".toolbar-search")) {
        results.style.display = "none";
      }
    });
  }

  function init() {
    $("perspective-name").textContent = personName(state.perspective);
    $("view-from-selected").addEventListener("click", () => {
      if (state.selected !== state.perspective) setPerspective(state.selected);
    });
    $("return-yahya").addEventListener("click", () => {
      if (state.perspective !== FAMILY.app.focus_id) setPerspective(FAMILY.app.focus_id);
      selectPerson(FAMILY.app.focus_id, true);
    });
    $("compare-run").addEventListener("click", showCompare);
    setupSearch();
    renderSidePanel();
    document.querySelectorAll('g.node[id^="flowchart-p_"]').forEach((node) => {
      const match = node.id.match(/flowchart-(p_.+)-\d+$/);
      if (!match) return;
      const personId = match[1].replace(/^p_/, "");
      node.addEventListener("click", () => selectPerson(personId, true));
    });
    ringFor(state.selected);
  }

  waitForRender(init);
})();
"""


def _with_viewer(core_html, data, mermaid_lib_js):
    """Adds the tiny interactive viewer around the generated diagram and
    embeds a complete offline snapshot plus the local Mermaid library."""
    snapshot = _viewer_snapshot(data)
    snapshot_json = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    snapshot_json = snapshot_json.replace("</", "<\\/")
    library = (mermaid_lib_js or "").replace("</script", "<\\/script")
    mermaid_tag = "<script>\n" + library + "\n</script>"

    toolbar = """
<div class="app-toolbar">
  <div class="toolbar-search">
    <input id="person-search" type="text"
      placeholder="Search person / تلاش کریں..." autocomplete="off">
    <div id="search-results" class="search-results"></div>
  </div>
  <div class="toolbar-state">
    <span>Perspective / نقطہ نظر: <strong id="perspective-name"></strong></span>
    <button id="view-from-selected" type="button">View family from selected / اس شخص کے نقطہ نظر سے</button>
    <button id="return-yahya" type="button">Return to Yahya / یحییٰ پر واپس</button>
  </div>
</div>
"""
    aside = """
<aside id="side-panel" class="side-panel">
  <div id="panel-photo" class="panel-photo"></div>
  <h2 id="panel-name" class="panel-name"></h2>
  <div id="panel-aliases" class="panel-aliases"></div>
  <div id="panel-facts" class="panel-facts"></div>
  <div id="panel-family" class="panel-family"></div>
  <h3 id="panel-rel-heading"></h3>
  <div id="panel-rel-main" class="rel-list"></div>
  <div id="panel-rel-additional"></div>
  <details id="perspective-all-box" class="panel-box">
    <summary>Relationships from perspective (all) / نقطہ نظر سے تمام رشتے</summary>
    <div id="perspective-all-list"></div>
  </details>
  <details id="compare-box" class="panel-box" open>
    <summary>Compare two people / دو افراد کا موازنہ</summary>
    <div class="compare-row">
      <label>A / A</label><select id="compare-a"></select>
      <label>B / B</label><select id="compare-b"></select>
      <button id="compare-run" type="button">Compare / موازنہ</button>
    </div>
    <div id="compare-out"></div>
  </details>
</aside>
"""

    core_html = core_html.replace("</style>", _VIEWER_CSS + "</style>", 1)
    core_html = core_html.replace(
        '<div class="diagram">',
        '<div class="app-shell">\n<div class="main-col">\n'
        + toolbar
        + '<div class="diagram">',
        1,
    )
    core_html = core_html.replace(
        "</div>\n<div class=\"details\">",
        "</div>\n</div>\n"
        + aside
        + "</div>\n<div class=\"details\">",
        1,
    )
    core_html = core_html.replace(
        '<script src="https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"></script>',
        '<script id="family-data" type="application/json">'
        + snapshot_json
        + "</script>\n"
        + mermaid_tag,
        1,
    )
    viewer_block = "<script>\n" + _VIEWER_JS + "\n</script>\n"
    body_end = core_html.rfind("</body>")
    if body_end == -1:
        raise ValueError("Generated HTML has no closing </body> tag.")
    core_html = (
        core_html[:body_end] + viewer_block + core_html[body_end:]
    )
    return core_html


def render_html(data, mermaid_text, mermaid_lib_js=""):
    escaped_mermaid = html_module.escape(mermaid_text, quote=False)
    revision = _revision_line(data)
    (
        _,
        _,
        _,
        _,
        _,
        couple_of_person,
        parents_of,
        _rels,
    ) = _couple_records(data)
    depths = _person_depths(data, parents_of)

    secondary_specs = []
    for group in data.get("sibling_groups", []):
        members = group.get("members", [])
        if group.get("ordered") or len(members) != 2:
            continue
        visual_depths = []
        for member in members:
            key = couple_of_person.get(member)
            visual_depths.append(
                max(depths[spouse] for spouse in key)
                if key
                else depths.get(member, 0)
            )
        secondary_specs.append(
            {
                "id": group["id"],
                "members": members,
                "label": _relationship_label(group),
                "lane": "above" if max(visual_depths) == 0 else "below",
            }
        )
    secondary_specs_json = json.dumps(secondary_specs, ensure_ascii=False)
    semantic_specs_json = json.dumps(
        _semantic_render_specs(data), ensure_ascii=False
    )
    sections_html = []
    for section in _placeholder_sections(data):
        html_lines = []
        list_open = False
        for line in section.splitlines():
            stripped = line.strip()
            if stripped.startswith("## "):
                if list_open:
                    html_lines.append("</ul>")
                    list_open = False
                html_lines.append(f"<h2>{html_module.escape(stripped[3:])}</h2>")
            elif stripped.startswith("- "):
                if not list_open:
                    html_lines.append('<ul class="detail-list">')
                    list_open = True
                content = stripped[2:].replace("**", "")
                html_lines.append(f"<li>{html_module.escape(content)}</li>")
        if html_lines:
            if list_open:
                html_lines.append("</ul>")
            sections_html.append("\n".join(html_lines))

    guide_html = "".join(
        f"<li>{html_module.escape(item)}</li>" for item in READING_GUIDE
    )
    derived_sections_html = _derived_focus_section_html(data)
    core_html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Family Relationships / خاندانی رشتے — {html_module.escape(revision)}</title>
<style>
  :root {{ color-scheme: light; }}
  html, body {{ margin: 0; padding: 0; background: #ffffff; color: #1a1a1a; }}
  body {{ font-family: "Segoe UI", system-ui, Tahoma, Arial, sans-serif; }}
  header {{ padding: 18px 24px 8px 24px; }}
  header h1 {{ margin: 0 0 4px 0; font-size: 24px; }}
  .meta {{ margin: 0; color: #555; font-size: 14px; }}
  .notice {{ margin: 12px 24px 0 24px; padding: 10px 14px; background: #f7f7f7; border-radius: 8px; color: #444; font-size: 13px; }}
  .notice ol {{ margin: 6px 0 0 0; padding-left: 20px; }}
  .notice li {{ margin: 2px 0; }}
  .diagram {{ margin: 14px 24px 24px 24px; border: 1px solid #e0e0e0; border-radius: 8px; overflow: auto; background: #ffffff; }}
  .diagram .mermaid {{ display: block; width: max-content; min-width: 100%; margin: 0 auto; }}
  .diagram .mermaid svg {{ max-width: none; }}
  .secondary-direct-relationships path {{
    fill: none;
    stroke: #777777;
    stroke-width: 2;
    stroke-dasharray: 7 6;
    stroke-linecap: round;
    stroke-linejoin: round;
  }}
  .secondary-direct-relationships text {{
    fill: #3f3f3f;
    font-family: "Segoe UI", system-ui, Tahoma, Arial, sans-serif;
    font-size: 14px;
  }}
  .semantic-family-connectors path {{
    fill: none;
    stroke: #333333;
    stroke-width: 1.5;
    stroke-linecap: round;
    stroke-linejoin: round;
  }}
  .details {{ margin: 0 24px 30px 24px; max-width: 1000px; }}
  .details h2 {{ font-size: 17px; margin: 22px 0 6px 0; }}
  .details li {{ margin: 2px 0; }}
  ul.detail-list {{ padding-left: 22px; }}
  .fallback {{ display: none; }}
</style>
</head>
<body>
<header>
  <h1>Family Relationships / خاندانی رشتے</h1>
  <p class="meta">{html_module.escape(revision)}</p>
</header>
<div class="notice">
  <strong>Generated from <code>family.db</code>.</strong> Update the data file, then run
  <code>python3.11 build_family.py</code>. This page and <code>family.md</code> are generated from
  the same Mermaid diagram string.
  <ol>
    {guide_html}
  </ol>
</div>
<div class="diagram">
  <pre class="mermaid">
{escaped_mermaid}
  </pre>
</div>
<div class="details">
  {derived_sections_html}
  {chr(10).join(sections_html)}
</div>
<script id="family-render-audit" type="application/json">{semantic_specs_json}</script>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"></script>
<script>
  const secondaryRelationships = {secondary_specs_json};
  const semanticRelationships = {semantic_specs_json};
  window.familyRenderAudit = semanticRelationships;

  function drawSemanticFamilyConnections() {{
    const svg = document.querySelector(".diagram svg");
    if (!svg) return;

    const svgRect = svg.getBoundingClientRect();
    const viewBox = svg.viewBox.baseVal;
    const scaleX = viewBox.width / svgRect.width;
    const scaleY = viewBox.height / svgRect.height;
    const nodeBox = (personId) => {{
      const node = svg.querySelector(`[id^="flowchart-p_${{personId}}-"]`);
      if (!node) throw new Error(`Missing Mermaid person node: ${{personId}}`);
      const rect = node.getBoundingClientRect();
      return {{
        top: viewBox.y + (rect.top - svgRect.top) * scaleY,
        bottom: viewBox.y + (rect.bottom - svgRect.top) * scaleY,
        centerX: viewBox.x + (rect.left + rect.width / 2 - svgRect.left) * scaleX,
      }};
    }};
    const edge = (source, target) =>
      [...svg.querySelectorAll("path.flowchart-link")].find((path) =>
        path.id.startsWith(`L_${{source}}_${{target}}_`)
      );

    const ns = "http://www.w3.org/2000/svg";
    const layer = document.createElementNS(ns, "g");
    layer.setAttribute("class", "semantic-family-connectors");
    layer.setAttribute("aria-label", "Person-card genealogy connectors");
    svg.querySelector("g.root").appendChild(layer);

    const addPath = (d, attributes = {{}}) => {{
      const path = document.createElementNS(ns, "path");
      path.setAttribute("d", d);
      for (const [name, value] of Object.entries(attributes)) {{
        if (value !== null && value !== undefined) path.setAttribute(name, value);
      }}
      layer.appendChild(path);
      return path;
    }};

    for (const marriage of semanticRelationships.marriages) {{
      const marriageEdge = edge(`p_${{marriage.people[0]}}`, `p_${{marriage.people[1]}}`);
      if (!marriageEdge) throw new Error(`Missing marriage edge: ${{marriage.id}}`);
      marriageEdge.setAttribute("data-marriage-id", marriage.id);
      marriageEdge.setAttribute("data-person-a", marriage.people[0]);
      marriageEdge.setAttribute("data-person-b", marriage.people[1]);
    }}

    for (const family of semanticRelationships.families) {{
      const trunk = edge(family.cluster, family.junction);
      if (!trunk) throw new Error(`Missing family trunk: ${{family.id}}`);
      trunk.setAttribute("data-family-id", family.id);
      trunk.setAttribute("data-semantic-route", "junction-trunk");
      const trunkStart = trunk.getPointAtLength(0);
      const parentBoxes = family.parents.map(nodeBox);
      const lowestParent = Math.max(...parentBoxes.map((box) => box.bottom));
      const joinY = lowestParent + Math.max(6, (trunkStart.y - lowestParent) / 2);

      for (let index = 0; index < family.parents.length; index += 1) {{
        const parentId = family.parents[index];
        const parent = parentBoxes[index];
        addPath(
          `M ${{parent.centerX}} ${{parent.bottom}} V ${{joinY}} H ${{trunkStart.x}}`,
          {{
            "data-family-id": family.id,
            "data-parent-id": parentId,
            "data-junction-id": family.junction,
          }}
        );
      }}
      addPath(
        `M ${{trunkStart.x}} ${{joinY}} V ${{trunkStart.y}}`,
        {{"data-family-id": family.id, "data-semantic-route": "parent-join"}}
      );

      for (const child of family.children) {{
        const target = child.cluster || `p_${{child.id}}`;
        const childEdge = edge(family.junction, target);
        if (!childEdge) throw new Error(`Missing child edge: ${{family.id}} -> ${{child.id}}`);
        childEdge.setAttribute("data-family-id", family.id);
        childEdge.setAttribute("data-child-id", child.id);
        childEdge.setAttribute("data-junction-id", family.junction);
        if (!child.cluster) continue;

        const markerEnd = childEdge.getAttribute("marker-end");
        childEdge.removeAttribute("marker-end");
        childEdge.setAttribute("data-semantic-route", "child-cluster-route");
        const end = childEdge.getPointAtLength(childEdge.getTotalLength());
        const childBox = nodeBox(child.id);
        const laneY = end.y + Math.max(6, (childBox.top - end.y) / 2);
        addPath(
          `M ${{end.x}} ${{end.y}} V ${{laneY}} H ${{childBox.centerX}} V ${{childBox.top}}`,
          {{
            "data-family-id": family.id,
            "data-child-id": child.id,
            "data-junction-id": family.junction,
            "data-semantic-route": "child-person-extension",
            "marker-end": markerEnd,
          }}
        );
      }}
    }}

    for (const fact of semanticRelationships.parent_child) {{
      if (fact.mode !== "direct") continue;
      const direct = edge(`p_${{fact.parent}}`, `p_${{fact.child}}`);
      if (!direct) throw new Error(`Missing direct parent-child edge: ${{fact.parent}} -> ${{fact.child}}`);
      direct.setAttribute("data-parent-id", fact.parent);
      direct.setAttribute("data-child-id", fact.child);
      direct.setAttribute("data-semantic-route", "direct-parent-child");
    }}
  }}

  function drawDirectSecondaryRelationships() {{
    const svg = document.querySelector(".diagram svg");
    if (!svg) return;

    // Layout-only routing helpers keep married people in compact LR couples
    // during Mermaid layout. They and Mermaid's provisional dotted paths are
    // never visible; the paths below connect the real person cards directly.
    svg.querySelectorAll('g.node[id*="flowchart-x_"]').forEach((node) => {{
      node.style.display = "none";
    }});
    svg.querySelectorAll("path.flowchart-link").forEach((path) => {{
      if (path.id.includes("_x_")) path.style.display = "none";
    }});

    const relationshipLabels = new Set(
      secondaryRelationships.map((relationship) => relationship.label)
    );
    svg.querySelectorAll("g.edgeLabel").forEach((label) => {{
      const text = label.textContent.replace(/\s+/g, " ").trim();
      if (relationshipLabels.has(text)) label.style.display = "none";
    }});

    const svgRect = svg.getBoundingClientRect();
    const viewBox = svg.viewBox.baseVal;
    const scaleX = viewBox.width / svgRect.width;
    const scaleY = viewBox.height / svgRect.height;
    const nodeBox = (personId) => {{
      const node = svg.querySelector(`[id^="flowchart-p_${{personId}}-"]`);
      if (!node) throw new Error(`Missing Mermaid person node: ${{personId}}`);
      const rect = node.getBoundingClientRect();
      return {{
        left: viewBox.x + (rect.left - svgRect.left) * scaleX,
        right: viewBox.x + (rect.right - svgRect.left) * scaleX,
        top: viewBox.y + (rect.top - svgRect.top) * scaleY,
        bottom: viewBox.y + (rect.bottom - svgRect.top) * scaleY,
        centerX: viewBox.x + (rect.left + rect.width / 2 - svgRect.left) * scaleX,
      }};
    }};

    const ns = "http://www.w3.org/2000/svg";
    const layer = document.createElementNS(ns, "g");
    layer.setAttribute("class", "secondary-direct-relationships");
    layer.setAttribute("aria-label", "Direct secondary relationships");
    svg.querySelector("g.root").appendChild(layer);

    const occupiedLanes = [];
    const laneFor = (first, second, side) => {{
      const minX = Math.min(first.centerX, second.centerX);
      const maxX = Math.max(first.centerX, second.centerX);
      let lane = side === "above"
        ? Math.min(first.top, second.top) - 80
        : Math.max(first.bottom, second.bottom) + 80;
      const step = side === "above" ? -55 : 55;
      while (occupiedLanes.some((used) =>
        used.side === side && Math.abs(used.y - lane) < 38 &&
        Math.max(minX, used.minX) < Math.min(maxX, used.maxX)
      )) lane += step;
      occupiedLanes.push({{side, y: lane, minX, maxX}});
      return lane;
    }};

    for (const relationship of secondaryRelationships) {{
      const first = nodeBox(relationship.members[0]);
      const second = nodeBox(relationship.members[1]);
      const laneY = laneFor(first, second, relationship.lane);
      const startY = relationship.lane === "above" ? first.top : first.bottom;
      const endY = relationship.lane === "above" ? second.top : second.bottom;

      const path = document.createElementNS(ns, "path");
      path.setAttribute(
        "d",
        `M ${{first.centerX}} ${{startY}} V ${{laneY}} H ${{second.centerX}} V ${{endY}}`
      );
      path.setAttribute("data-relationship-id", relationship.id);
      path.setAttribute("data-person-a", relationship.members[0]);
      path.setAttribute("data-person-b", relationship.members[1]);
      layer.appendChild(path);

      const label = document.createElementNS(ns, "text");
      label.setAttribute("x", String((first.centerX + second.centerX) / 2));
      label.setAttribute("y", String(laneY - 9));
      label.setAttribute("text-anchor", "middle");
      label.setAttribute("data-relationship-label", relationship.id);
      label.textContent = relationship.label;
      layer.appendChild(label);

      const labelBox = label.getBBox();
      const backing = document.createElementNS(ns, "rect");
      backing.setAttribute("x", String(labelBox.x - 5));
      backing.setAttribute("y", String(labelBox.y - 2));
      backing.setAttribute("width", String(labelBox.width + 10));
      backing.setAttribute("height", String(labelBox.height + 4));
      backing.setAttribute("rx", "3");
      backing.setAttribute("fill", "#ffffff");
      backing.setAttribute("data-relationship-label-backing", relationship.id);
      layer.insertBefore(backing, label);
    }}
  }}

  mermaid.initialize({{
    startOnLoad: false,
    theme: "neutral",
    flowchart: {{
      htmlLabels: true,
      useMaxWidth: false,
      curve: "basis",
      padding: 10
    }}
  }});
  mermaid.run({{querySelector: ".mermaid"}}).then(() => {{
    drawSemanticFamilyConnections();
    drawDirectSecondaryRelationships();
    window.familyRenderReady = true;
  }});
</script>
</body>
</html>
"""
    return _with_viewer(core_html, data, mermaid_lib_js)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Validate family.db (SQLite is the structured source of truth) "
            "and generate family.md + family.html from one Mermaid diagram."
        )
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate without rewriting outputs",
    )
    parser.add_argument(
        "--migrate-json-to-sqlite",
        action="store_true",
        help=(
            "One-time migration: import a verified JSON snapshot into "
            "family.db, then prove JSON <=> SQLite parity."
        ),
    )
    parser.add_argument(
        "--json-path",
        default=str(DATA_PATH),
        help="JSON snapshot to use with --migrate-json-to-sqlite",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "With --migrate-json-to-sqlite: rebuild an existing non-empty "
            "family.db from the JSON snapshot."
        ),
    )
    parser.add_argument(
        "--mark-migration-complete",
        action="store_true",
        help=(
            "After certified migration: bump the project revision exactly "
            "once (5 -> 6) using the current implementation date."
        ),
    )
    args = parser.parse_args()

    if args.migrate_json_to_sqlite:
        migrate_json_to_sqlite(args.json_path, force=args.force)
        return

    if args.mark_migration_complete:
        if not DB_PATH.exists():
            raise FileNotFoundError("family.db is missing; run the migration first.")
        connection = _connect(DB_PATH)
        try:
            row = connection.execute(
                "SELECT value FROM metadata WHERE key = 'revision'"
            ).fetchone()
            current_revision = int(row["value"]) if row else None
            if current_revision != 5:
                raise ValueError(
                    "Migration completion marker expects revision 5; "
                    f"found {current_revision!r}."
                )
            connection.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES ('revision', '6')"
            )
            connection.execute(
                "INSERT OR REPLACE INTO metadata (key, value) "
                "VALUES ('updated', '2026-09-03')"
            )
            connection.commit()
            print("Revision bumped exactly once: 5 -> 6 (2026-09-03).")
        finally:
            connection.close()
        return

    if not args.check and DB_PATH.exists():
        connection = _connect(DB_PATH)
        try:
            _register_project_source_files(connection)
            connection.commit()
        finally:
            connection.close()

    data = load_data()
    validate(data)

    mermaid_text = build_mermaid(data)
    audit = audit_render_mapping(data, mermaid_text)
    derived_audit = _audit_derived(data)
    viewer_audit = _kinship_regression_audit(data)

    if not args.check:
        if not MERMAID_LIB_PATH.exists():
            raise FileNotFoundError(
                f"Missing local Mermaid library: {MERMAID_LIB_PATH}. "
                "The standalone family.html cannot be built offline without it."
            )
        mermaid_lib_js = MERMAID_LIB_PATH.read_text(encoding="utf-8")
        OUTPUT_MD_PATH.write_text(
            render_markdown(data, mermaid_text), encoding="utf-8"
        )
        OUTPUT_HTML_PATH.write_text(
            render_html(data, mermaid_text, mermaid_lib_js), encoding="utf-8"
        )
        print(f"Wrote {OUTPUT_MD_PATH}")
        print(f"Wrote {OUTPUT_HTML_PATH}")

    print(
        f"Valid: {len(data['people'])} people, "
        f"{len(data['parent_child'])} parent-child facts, "
        f"{len(data['marriages'])} marriages."
    )
    print(
        "Semantic render mapping: "
        f"{audit['parent_child']} parent-child, "
        f"{audit['marriages']} marriage, "
        f"{audit['sibling_groups']} sibling-group records."
    )
    print(
        "Derived kinship audit: "
        f"{derived_audit['focus_cousin_paths']} focus-person cousin paths."
    )
    print(
        "Viewer kinship audit: "
        f"{viewer_audit} people; arbitrary-perspective checks PASS."
    )


if __name__ == "__main__":
    main()
