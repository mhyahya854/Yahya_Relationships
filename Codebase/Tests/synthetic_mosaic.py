"""Fictional Mosaic Data Root generator shared by local and CI tests.

The graph is deliberately invented. No source file or database is read from
the working checkout. Call ``build(root)`` only with a disposable directory.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from app.backend import db
from app.backend.data_root.manager import DataRootManager
from app.backend.domain.canonical.ids import generate_canonical_person_id, normalize_name
from app.backend.domain.canonical.template import initialize_person_folder


PEOPLE = (
    ("Mira Rahim", "female", 1993, "Me"),
    ("Elias Calder", "male", 1966, "Family"),
    ("Salma Rahim", "female", 1968, "Family"),
    ("Sami Calder", "male", 1996, "Family"),
    ("Qadir Rahim", "male", 1939, "Family"),
    ("Mahira Rahim", "female", 1942, "Family"),
    ("Adnan Calder", "male", 1937, "Family"),
    ("Soraya Calder", "female", 1940, "Family"),
    ("Layla Rahim", "female", 1970, "Family"),
    ("Kamal Calder", "male", 1969, "Family"),
    ("Noor Rahim", "female", 2001, "Family"),
    ("Rafi Calder", "male", 2003, "Family"),
    ("Aika Calder-Rahim", "female", 2002, "Family"),
    ("Darya Sol", "female", 1992, "Friends"),
    ("Quinn Aster", "unknown", 1988, "Friends"),
)

PARENTS = (
    ("Qadir Rahim", "Salma Rahim", "father"),
    ("Mahira Rahim", "Salma Rahim", "mother"),
    ("Qadir Rahim", "Layla Rahim", "father"),
    ("Mahira Rahim", "Layla Rahim", "mother"),
    ("Adnan Calder", "Elias Calder", "father"),
    ("Soraya Calder", "Elias Calder", "mother"),
    ("Adnan Calder", "Kamal Calder", "father"),
    ("Soraya Calder", "Kamal Calder", "mother"),
    ("Elias Calder", "Mira Rahim", "father"),
    ("Salma Rahim", "Mira Rahim", "mother"),
    ("Elias Calder", "Sami Calder", "father"),
    ("Salma Rahim", "Sami Calder", "mother"),
    ("Layla Rahim", "Noor Rahim", "mother"),
    ("Kamal Calder", "Rafi Calder", "father"),
    ("Kamal Calder", "Aika Calder-Rahim", "father"),
    ("Layla Rahim", "Aika Calder-Rahim", "mother"),
)

MARRIAGES = (
    ("Qadir Rahim", "Mahira Rahim", 1962),
    ("Adnan Calder", "Soraya Calder", 1961),
    ("Elias Calder", "Salma Rahim", 1991),
    ("Kamal Calder", "Layla Rahim", 1999),
)

BRANCHES = {
    "Qadir Rahim": "maternal", "Mahira Rahim": "maternal",
    "Salma Rahim": "maternal", "Layla Rahim": "maternal",
    "Adnan Calder": "paternal", "Soraya Calder": "paternal",
    "Elias Calder": "paternal", "Kamal Calder": "paternal",
}


def build(root: Path, *, include_backup: bool = False) -> dict[str, str]:
    root = root.resolve()
    if root.exists() and any(root.iterdir()):
        raise FileExistsError("Synthetic fixture destination must be empty")
    DataRootManager.assert_private_root(root)
    DataRootManager.ensure_structure(root, create=True, canonical=True)
    database = root / "Database" / "relationships.db"
    db.initialize_database(database)
    identifiers = {name: generate_canonical_person_id(name) for name, *_ in PEOPLE}
    with closing(db.get_connection(database)) as connection, connection:
        now = db.utc_now()
        for order, (name, gender, birth_year, category) in enumerate(PEOPLE):
            person_id = identifiers[name]
            connection.execute(
                "INSERT INTO people (id,name,birth_year,gender,category,branch,display_order,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (person_id, name, birth_year, gender, category, BRANCHES.get(name), order, now, now),
            )
            group = "family" if category in {"Me", "Family"} else "friends" if category == "Friends" else "other"
            connection.execute("INSERT INTO person_groups (person_id,group_id,is_primary) VALUES (?,?,1)", (person_id, group))
            initialize_person_folder(root / "People" / category / person_id, person_id, name,
                                     primary_category=category, birth_year=birth_year, gender=gender)
        connection.execute("INSERT INTO aliases (person_id,alias,display_order) VALUES (?,?,0)",
                           (identifiers["Darya Sol"], "Dari"))
        connection.execute(
            "INSERT INTO unresolved_people (id,label,notes,created_at) VALUES (?,?,?,?)",
            ("unknown_person--UP0001", "Unknown garden volunteer", "Fictional unresolved test record", now),
        )
        for parent, child, role in PARENTS:
            connection.execute("INSERT INTO parent_child (parent_id,child_id,role,kind) VALUES (?,?,?,'biological')",
                               (identifiers[parent], identifiers[child], role))
        for order, (first, second, year) in enumerate(MARRIAGES):
            a, b = sorted((identifiers[first], identifiers[second]))
            connection.execute("INSERT INTO marriages (spouse_a,spouse_b,status,year,display_order) VALUES (?,?,'married',?,?)",
                               (a, b, year, order))
        for group_id, members in (("mira_sami", ("Mira Rahim", "Sami Calder")),
                                  ("salma_layla", ("Salma Rahim", "Layla Rahim")),
                                  ("elias_kamal", ("Elias Calder", "Kamal Calder"))):
            connection.execute("INSERT INTO sibling_groups (id,is_ordered,type,label_en,display_order) VALUES (?,1,'full',?,0)",
                               (group_id, "Synthetic siblings"))
            for order, name in enumerate(members, 1):
                connection.execute("INSERT INTO sibling_group_members (group_id,person_id,member_order) VALUES (?,?,?)",
                                   (group_id, identifiers[name], order))
        connection.execute("INSERT OR REPLACE INTO metadata (key,value) VALUES ('focus_person',?)", (identifiers["Mira Rahim"],))
        connection.execute("INSERT OR REPLACE INTO metadata (key,value) VALUES ('revision','1')")
        connection.execute("INSERT INTO general_relationships (person_a,person_b,type,directionality) VALUES (?,?,'friend','symmetric')",
                           tuple(sorted((identifiers["Mira Rahim"], identifiers["Darya Sol"]))))
        connection.execute(
            "INSERT INTO general_relationships (person_a,person_b,type,directionality,direction_from) "
            "VALUES (?,?,'mentor','directional',?)",
            (*sorted((identifiers["Darya Sol"], identifiers["Quinn Aster"])), identifiers["Darya Sol"]),
        )
    journal = root / "People" / "Me" / identifiers["Mira Rahim"] / "journal(personal thoughts).md"
    journal.write_text("# Synthetic journal\n\nThe garden concert was fictional.\n", encoding="utf-8")
    raw_sample = "Synthetic Raw intake sample.\n"
    (root / "Raw" / "synthetic-note.txt").write_text(raw_sample, encoding="utf-8")
    (root / "Raw" / "synthetic-note-copy.txt").write_text(raw_sample, encoding="utf-8")
    (root / "Database" / "Config" / "state.json").write_text(
        json.dumps({"perspective_person_id": identifiers["Mira Rahim"]}) + "\n", encoding="utf-8")
    if include_backup:
        from app.backend.domain.backups import create_backup

        create_backup("Synthetic fixture snapshot", root=root)
    return identifiers


def build_legacy(root: Path) -> dict[str, str]:
    """Build a fictional schema-v2 source for the Phase 11 migration tests."""
    root = root.resolve()
    if root.exists() and any(root.iterdir()):
        raise FileExistsError("Synthetic legacy fixture destination must be empty")
    DataRootManager.assert_private_root(root)
    database = root / "Database" / "Main" / "family.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    ids = {name: normalize_name(name) for name, *_ in PEOPLE}
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        db._bootstrap_new_database(connection, target_schema=2)
        now = db.utc_now()
        for order, (name, gender, birth_year, category) in enumerate(PEOPLE):
            person_id = ids[name]
            connection.execute(
                "INSERT INTO people (id,name,birth_year,gender,branch,display_order) VALUES (?,?,?,?,?,?)",
                (person_id, name, birth_year, gender, BRANCHES.get(name), order),
            )
            group = "family" if category in {"Me", "Family"} else "friends"
            connection.execute(
                "INSERT INTO person_groups (person_id,group_id,is_primary) VALUES (?,?,1)",
                (person_id, group),
            )
            folder = root / "Database" / "People" / ("Me" if category == "Me" else "Family") / person_id
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "journal.md").write_text(
                f"# Fictional journal for {name}\n\nA garden concert in the invented town.\n",
                encoding="utf-8",
            )
        connection.execute(
            "INSERT INTO aliases (person_id,alias,display_order) VALUES (?,?,0)",
            (ids["Darya Sol"], "Dari"),
        )
        for parent, child, role in PARENTS:
            connection.execute(
                "INSERT INTO parent_child (parent_id,child_id,role,kind) VALUES (?,?,?,'biological')",
                (ids[parent], ids[child], role),
            )
        for order, (first, second, year) in enumerate(MARRIAGES):
            a, b = sorted((ids[first], ids[second]))
            connection.execute(
                "INSERT INTO marriages (spouse_a,spouse_b,status,year,display_order) VALUES (?,?,'married',?,?)",
                (a, b, year, order),
            )
        for group_id, members in (
            ("mira_sami", ("Mira Rahim", "Sami Calder")),
            ("salma_layla", ("Salma Rahim", "Layla Rahim")),
            ("elias_kamal", ("Elias Calder", "Kamal Calder")),
        ):
            connection.execute(
                "INSERT INTO sibling_groups (id,is_ordered,type,label_en,display_order) VALUES (?,1,'full',?,0)",
                (group_id, "Synthetic siblings"),
            )
            for order, name in enumerate(members, 1):
                connection.execute(
                    "INSERT INTO sibling_group_members (group_id,person_id,member_order) VALUES (?,?,?)",
                    (group_id, ids[name], order),
                )
        connection.execute(
            "INSERT OR REPLACE INTO metadata (key,value) VALUES ('focus_person',?)",
            (ids["Mira Rahim"],),
        )
        connection.execute(
            "INSERT OR REPLACE INTO metadata (key,value) VALUES ('revision','1')"
        )
        connection.execute(
            "INSERT INTO general_relationships (person_a,person_b,type,directionality,created_at,updated_at) "
            "VALUES (?,?,'friend','symmetric',?,?)",
            (*sorted((ids["Mira Rahim"], ids["Darya Sol"])), now, now),
        )
        connection.commit()
    return ids
