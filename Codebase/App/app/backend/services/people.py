"""People directory and management service."""

import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .. import config, db
from ..domain.mutations.history import (
    pop_latest_snapshot,
    record_pre_mutation_snapshot,
    update_latest_filesystem_manifest,
)
from . import errors

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_]{0,119}$")


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "person"


def _next_person_id(connection: sqlite3.Connection, base: str) -> str:
    candidate = base
    counter = 2
    while True:
        exists = connection.execute(
            "SELECT 1 FROM people WHERE id = ?", (candidate,)
        ).fetchone()
        if exists is None:
            return candidate
        candidate = f"{base}_{counter}"
        counter += 1


def group_rows(connection: sqlite3.Connection, person_id: str) -> list[dict]:
    rows = connection.execute(
        """
        SELECT g.id, g.name, g.slug, g.kind, pg.is_primary
        FROM groups g
        JOIN person_groups pg ON pg.group_id = g.id
        WHERE pg.person_id = ?
        ORDER BY pg.is_primary DESC, g.display_order, g.name
        """,
        (person_id,),
    ).fetchall()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "slug": row["slug"],
            "kind": row["kind"],
            "is_primary": bool(row["is_primary"]),
        }
        for row in rows
    ]


def _person_serialize(connection: sqlite3.Connection, row) -> dict:
    aliases = [
        alias["alias"]
        for alias in connection.execute(
            """
            SELECT alias FROM aliases WHERE person_id = ?
            ORDER BY display_order
            """,
            (row["id"],),
        )
    ]
    folder_path = None
    folder_exists = False
    journal_exists = False
    try:
        folder_path = db.find_person_folder(connection, row["id"])
        if folder_path is not None and folder_path.is_dir():
            folder_exists = True
            journal_file = folder_path / "journal.md"
            journal_exists = journal_file.is_file()
    except (LookupError, OSError):
        folder_path = None
        folder_exists = False
        journal_exists = False

    return {
        "id": row["id"],
        "name": row["name"],
        "aliases": aliases,
        "birth_year": row["birth_year"],
        "gender": row["gender"],
        "marital_status": row["marital_status"],
        "branch": row["branch"],
        "note_en": row["note_en"],
        "note_ur": row["note_ur"],
        "photo_path": row["photo_path"],
        "groups": group_rows(connection, row["id"]),
        "folder": str(folder_path) if folder_exists else None,
        "folder_exists": folder_exists,
        "journal_exists": journal_exists,
    }


def list_people(*, query: str | None = None, group_id: str | None = None) -> list[dict]:
    connection = db.get_connection()
    try:
        sql = [
            """
            SELECT p.* FROM people p
            WHERE 1 = 1
            """
        ]
        params: list = []
        if group_id:
            sql.append(
                "AND p.id IN (SELECT person_id FROM person_groups WHERE group_id = ?)"
            )
            params.append(group_id)
        if query:
            sql.append(
                """
                AND (
                  p.name LIKE ? ESCAPE '\\'
                  OR p.id IN (
                    SELECT person_id FROM aliases WHERE alias LIKE ? ESCAPE '\\'
                  )
                )
                """
            )
            escaped = query.replace("%", "\\%").replace("_", "\\_")
            like = f"%{escaped}%"
            params.extend([like, like])
        sql.append("ORDER BY p.display_order, p.name")
        rows = connection.execute(" ".join(sql), params).fetchall()
        return [_person_serialize(connection, row) for row in rows]
    finally:
        connection.close()


def get_person(person_id: str) -> dict:
    connection = db.get_connection()
    try:
        row = connection.execute(
            "SELECT * FROM people WHERE id = ?", (person_id,)
        ).fetchone()
        if row is None:
            raise errors.NotFoundError(f"Unknown person id: {person_id}")
        return _person_serialize(connection, row)
    finally:
        connection.close()


def check_duplicate_person(name: str, aliases: list[str] | None = None) -> list[dict]:
    """Check for potential duplicate people based on name and aliases."""
    if not name or not name.strip():
        return []
    target_norm = re.sub(r"\s+", " ", name.strip().lower())
    target_tokens = set(target_norm.split())
    target_aliases = {re.sub(r"\s+", " ", a.strip().lower()) for a in (aliases or []) if a.strip()}

    all_people = list_people()
    candidates = []
    for p in all_people:
        p_name_norm = re.sub(r"\s+", " ", p["name"].strip().lower())
        p_tokens = set(p_name_norm.split())
        p_aliases = {re.sub(r"\s+", " ", a.strip().lower()) for a in p.get("aliases", [])}

        match_reason = None
        if target_norm == p_name_norm:
            match_reason = "exact name match"
        elif target_norm in p_aliases:
            match_reason = "alias match"
        elif target_aliases and p_name_norm in target_aliases:
            match_reason = "alias match"
        elif target_aliases and target_aliases.intersection(p_aliases):
            match_reason = "shared alias match"
        elif target_norm in p_name_norm or p_name_norm in target_norm:
            match_reason = "name substring match"
        elif len(target_tokens) > 0 and (target_tokens.issubset(p_tokens) or p_tokens.issubset(target_tokens)):
            match_reason = "name token overlap"

        if match_reason:
            candidates.append({
                "id": p["id"],
                "name": p["name"],
                "aliases": p.get("aliases", []),
                "groups": p.get("groups", []),
                "reason": match_reason,
            })
    return candidates


def create_person(
    *,
    name: str,
    aliases: list[str] | None = None,
    birth_year: int | None = None,
    gender: str | None = None,
    marital_status: str | None = None,
    branch: str | None = None,
    note_en: str | None = None,
    note_ur: str | None = None,
    group_id: str | None = None,
    group_ids: list[str] | None = None,
    primary_group_id: str | None = None,
    origin: str = "user",
) -> dict:
    if not name or not str(name).strip():
        raise errors.ValidationError("Person name is required.")
    if birth_year is not None and not 1800 <= int(birth_year) <= 2100:
        raise errors.ValidationError("Birth year must be between 1800 and 2100.")
    if gender not in (None, "male", "female", "unknown"):
        raise errors.ValidationError("Unsupported gender value.")
    if marital_status not in (None, "single"):
        raise errors.ValidationError("Unsupported marital status value.")

    from ..data_root.errors import DataRootReadOnlyError
    from ..data_root.manager import DataRootManager
    from ..domain.maintenance import check_maintenance_lock

    check_maintenance_lock()
    if DataRootManager.is_read_only():
        raise DataRootReadOnlyError()

    record_pre_mutation_snapshot(f"Created person: {name}")

    connection = db.get_connection()
    target_folder: Path | None = None
    target_journal: Path | None = None
    folder_existed_before = True
    journal_existed_before = True
    snapshot_committed = False
    try:
        connection.execute("BEGIN")
        base = _slugify(str(name).strip())
        person_id = _next_person_id(connection, base)
        max_order = connection.execute(
            "SELECT COALESCE(MAX(display_order), -1) AS m FROM people"
        ).fetchone()["m"]
        connection.execute(
            """
            INSERT INTO people (
              id, name, birth_year, gender, marital_status, branch,
              note_en, note_ur, display_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                person_id,
                str(name).strip(),
                birth_year,
                gender,
                marital_status,
                branch,
                note_en,
                note_ur,
                int(max_order) + 1,
            ),
        )
        for index, alias in enumerate(aliases or []):
            alias = str(alias).strip()
            if alias:
                connection.execute(
                    """
                    INSERT INTO aliases (person_id, alias, display_order)
                    VALUES (?, ?, ?)
                    """,
                    (person_id, alias, index),
                )

        # Resolve group_ids
        target_group_ids = []
        if group_ids:
            for gid in group_ids:
                s = str(gid).strip()
                if s and s not in target_group_ids:
                    target_group_ids.append(s)
        elif group_id:
            target_group_ids = [str(group_id).strip()]
        if not target_group_ids:
            target_group_ids = ["other"]

        # Validate that all groups exist
        matched_groups = []
        for gid in target_group_ids:
            grp = connection.execute(
                "SELECT id, slug FROM groups WHERE id = ? OR LOWER(id) = LOWER(?) OR LOWER(slug) = LOWER(?)",
                (gid, gid, gid),
            ).fetchone()
            if grp is None:
                raise errors.ValidationError(f"Unknown group id: {gid}")
            if grp["id"] not in matched_groups:
                matched_groups.append(grp["id"])

        # Determine primary group
        primary_id = None
        if primary_group_id:
            for gid in matched_groups:
                if gid.lower() == str(primary_group_id).lower():
                    primary_id = gid
                    break
        if not primary_id and matched_groups:
            primary_id = matched_groups[0]

        for gid in matched_groups:
            connection.execute(
                """
                INSERT INTO person_groups (person_id, group_id, is_primary)
                VALUES (?, ?, ?)
                """,
                (person_id, gid, 1 if gid == primary_id else 0),
            )

        source_id = db.register_source(connection, origin=origin)
        db.link_fact_source(connection, source_id, "people", person_id, origin=origin)

        # Canonical filesystem creation with failure-atomicity
        target_folder = db.expected_person_folder(connection, person_id)
        target_journal = target_folder / "journal.md"
        folder_existed_before = target_folder.exists()
        journal_existed_before = target_journal.exists()

        try:
            journal_path = db.ensure_journal(connection, person_id)
            if not journal_path.is_file():
                raise OSError(f"Canonical journal.md not created at {journal_path}")
        except Exception as fs_exc:
            raise errors.StorageError(
                f"Failed to create canonical journal for '{name}': {fs_exc}",
                details={"person_id": person_id, "path": str(target_journal)},
            ) from fs_exc

        # Both DB and filesystem are verified
        connection.commit()
        snapshot_committed = True
        update_latest_filesystem_manifest({"created_paths": [str(journal_path)]})
        return get_person(person_id)
    except Exception:
        if not snapshot_committed:
            try:
                connection.rollback()
            except Exception:
                pass
            if not journal_existed_before and target_journal is not None and target_journal.exists():
                try:
                    target_journal.unlink()
                except OSError:
                    pass
            if not folder_existed_before and target_folder is not None and target_folder.exists():
                try:
                    shutil.rmtree(target_folder)
                except OSError:
                    pass
            pop_latest_snapshot()
        raise
    finally:
        connection.close()




def update_person(
    person_id: str,
    *,
    name: str | None = None,
    aliases: list[str] | None = None,
    birth_year: int | None = None,
    clear_birth_year: bool = False,
    gender: str | None = None,
    clear_gender: bool = False,
    marital_status: str | None = None,
    clear_marital_status: bool = False,
    branch: str | None = None,
    note_en: str | None = None,
    clear_note_en: bool = False,
    note_ur: str | None = None,
    clear_note_ur: bool = False,
    group_ids: list[str] | None = None,
    primary_group_id: str | None = None,
    origin: str = "user",
) -> dict:
    record_pre_mutation_snapshot(f"Updated person: {person_id}")

    connection = db.get_connection()
    try:
        row = connection.execute(
            "SELECT * FROM people WHERE id = ?", (person_id,)
        ).fetchone()
        if row is None:
            raise errors.NotFoundError(f"Unknown person id: {person_id}")
        fields = []
        params: list = []
        if name is not None:
            if not str(name).strip():
                raise errors.ValidationError("Person name is required.")
            fields.append("name = ?")
            params.append(str(name).strip())
        if birth_year is not None and not 1800 <= int(birth_year) <= 2100:
            raise errors.ValidationError("Birth year must be between 1800 and 2100.")
        if birth_year is not None:
            fields.append("birth_year = ?")
            params.append(birth_year)
        elif clear_birth_year:
            fields.append("birth_year = NULL")
        if gender is not None:
            if gender not in ("male", "female", "unknown"):
                raise errors.ValidationError("Unsupported gender value.")
            fields.append("gender = ?")
            params.append(gender)
        elif clear_gender:
            fields.append("gender = NULL")
        if marital_status is not None:
            if marital_status not in ("single",):
                raise errors.ValidationError("Unsupported marital status value.")
            fields.append("marital_status = ?")
            params.append(marital_status)
        elif clear_marital_status:
            fields.append("marital_status = NULL")
        if branch is not None:
            fields.append("branch = ?")
            params.append(branch)
        if note_en is not None:
            fields.append("note_en = ?")
            params.append(note_en)
        elif clear_note_en:
            fields.append("note_en = NULL")
        if note_ur is not None:
            fields.append("note_ur = ?")
            params.append(note_ur)
        elif clear_note_ur:
            fields.append("note_ur = NULL")

        group_moves = []
        if group_ids is not None:
            target_group_ids = []
            for gid in group_ids:
                s = str(gid).strip()
                if s and s not in target_group_ids:
                    target_group_ids.append(s)
            if not target_group_ids:
                raise errors.ValidationError("A person must belong to at least one group.")

            matched_groups = []
            for gid in target_group_ids:
                grp = connection.execute(
                    "SELECT id, slug FROM groups WHERE id = ? OR LOWER(id) = LOWER(?) OR LOWER(slug) = LOWER(?)",
                    (gid, gid, gid),
                ).fetchone()
                if grp is None:
                    raise errors.ValidationError(f"Unknown group id: {gid}")
                if grp["id"] not in matched_groups:
                    matched_groups.append(grp["id"])

            old_primary_row = connection.execute(
                """
                SELECT g.id, g.slug FROM groups g
                JOIN person_groups pg ON pg.group_id = g.id
                WHERE pg.person_id = ? AND pg.is_primary = 1
                """,
                (person_id,),
            ).fetchone()

            new_primary_id = None
            if primary_group_id:
                for gid in matched_groups:
                    if gid.lower() == str(primary_group_id).lower():
                        new_primary_id = gid
                        break
            if not new_primary_id:
                if old_primary_row and old_primary_row["id"] in matched_groups:
                    new_primary_id = old_primary_row["id"]
                else:
                    new_primary_id = matched_groups[0]

            new_primary_group = connection.execute(
                "SELECT id, slug FROM groups WHERE id = ?", (new_primary_id,)
            ).fetchone()

            if old_primary_row and new_primary_group and old_primary_row["slug"] != new_primary_group["slug"]:
                old_folder = config.PEOPLE_DIR / old_primary_row["slug"] / person_id
                target_folder = config.PEOPLE_DIR / new_primary_group["slug"] / person_id
                if old_folder.exists() and old_folder.resolve() != target_folder.resolve():
                    if target_folder.exists():
                        raise errors.InvalidOperationError(
                            "A person folder already exists under the target group. "
                            "Resolve the duplicate folders manually before moving.",
                            code="FOLDER_EXISTS",
                        )
                    group_moves.append((old_folder, target_folder))

        if fields or aliases is not None or group_ids is not None:
            connection.execute("BEGIN")
            if fields:
                params.append(person_id)
                connection.execute(
                    f"UPDATE people SET {', '.join(fields)} WHERE id = ?", params
                )
            if aliases is not None:
                connection.execute(
                    "DELETE FROM aliases WHERE person_id = ?", (person_id,)
                )
                for index, alias in enumerate(aliases):
                    alias = str(alias).strip()
                    if alias:
                        connection.execute(
                            """
                            INSERT INTO aliases (person_id, alias, display_order)
                            VALUES (?, ?, ?)
                            """,
                            (person_id, alias, index),
                        )
            if group_ids is not None:
                connection.execute("DELETE FROM person_groups WHERE person_id = ?", (person_id,))
                for gid in matched_groups:
                    connection.execute(
                        """
                        INSERT INTO person_groups (person_id, group_id, is_primary)
                        VALUES (?, ?, ?)
                        """,
                        (person_id, gid, 1 if gid == new_primary_id else 0),
                    )

            source_id = db.register_source(connection, origin=origin)
            db.link_fact_source(
                connection, source_id, "people", person_id, origin=origin
            )
            connection.commit()

            # Execute folder move safely if primary changed
            for old_f, target_f in group_moves:
                if old_f.exists() and not target_f.exists():
                    target_f.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(old_f), str(target_f))
                    update_latest_filesystem_manifest({
                        "moves": [{"from": str(old_f), "to": str(target_f)}]
                    })

        return get_person(person_id)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def get_person_profile(person_id: str, perspective_id: str | None = None) -> dict:
    """Aggregate complete profile for a person: identity, direct family facts,
    general relationships, perspective-interpreted kinship, and journal preview."""
    connection = db.get_connection()
    try:
        row = connection.execute(
            "SELECT * FROM people WHERE id = ?", (person_id,)
        ).fetchone()
        if row is None:
            raise errors.NotFoundError(f"Unknown person id: {person_id}")
        person_brief = _person_serialize(connection, row)

        # 1. Direct Family Facts
        # Parents
        parents_rows = connection.execute(
            """
            SELECT p.id, p.name, p.gender, p.birth_year, pc.role, pc.kind
            FROM parent_child pc
            JOIN people p ON pc.parent_id = p.id
            WHERE pc.child_id = ?
            ORDER BY pc.id
            """,
            (person_id,),
        ).fetchall()
        parents = [
            {
                "id": r["id"],
                "name": r["name"],
                "gender": r["gender"],
                "birth_year": r["birth_year"],
                "role": r["role"],
                "kind": r["kind"],
            }
            for r in parents_rows
        ]

        # Children
        children_rows = connection.execute(
            """
            SELECT p.id, p.name, p.gender, p.birth_year, pc.role, pc.kind
            FROM parent_child pc
            JOIN people p ON pc.child_id = p.id
            WHERE pc.parent_id = ?
            ORDER BY pc.id
            """,
            (person_id,),
        ).fetchall()
        children = [
            {
                "id": r["id"],
                "name": r["name"],
                "gender": r["gender"],
                "birth_year": r["birth_year"],
                "role": r["role"],
                "kind": r["kind"],
            }
            for r in children_rows
        ]

        # Spouses
        spouses_rows = connection.execute(
            """
            SELECT p.id, p.name, p.gender, p.birth_year, m.status, m.year, m.children_status
            FROM marriages m
            JOIN people p ON (p.id = CASE WHEN m.spouse_a = ? THEN m.spouse_b ELSE m.spouse_a END)
            WHERE m.spouse_a = ? OR m.spouse_b = ?
            ORDER BY m.display_order, m.id
            """,
            (person_id, person_id, person_id),
        ).fetchall()
        spouses = [
            {
                "id": r["id"],
                "name": r["name"],
                "gender": r["gender"],
                "birth_year": r["birth_year"],
                "status": r["status"],
                "year": r["year"],
                "children_status": r["children_status"],
            }
            for r in spouses_rows
        ]

        # Siblings
        siblings_rows = connection.execute(
            """
            SELECT DISTINCT p.id, p.name, p.gender, p.birth_year, sg.type as sibling_type
            FROM sibling_group_members sgm
            JOIN sibling_groups sg ON sg.id = sgm.group_id
            JOIN sibling_group_members sgm2 ON sgm2.group_id = sg.id
            JOIN people p ON p.id = sgm2.person_id
            WHERE sgm.person_id = ? AND sgm2.person_id <> ?
            ORDER BY sgm2.member_order, p.display_order
            """,
            (person_id, person_id),
        ).fetchall()
        siblings = [
            {
                "id": r["id"],
                "name": r["name"],
                "gender": r["gender"],
                "birth_year": r["birth_year"],
                "type": r["sibling_type"],
            }
            for r in siblings_rows
        ]

        # 2. General Relationships
        from ..kinship import labels
        gen_rows = connection.execute(
            """
            SELECT * FROM general_relationships
            WHERE person_a = ? OR person_b = ?
            ORDER BY id
            """,
            (person_id, person_id),
        ).fetchall()
        general_relationships = []
        for gr in gen_rows:
            other_id = gr["person_b"] if gr["person_a"] == person_id else gr["person_a"]
            other_p = connection.execute("SELECT id, name FROM people WHERE id = ?", (other_id,)).fetchone()
            if other_p:
                normalized = labels.normalize_general_entry(
                    gr,
                    from_person=person_id,
                    label_a_to_b=gr["label_a_to_b"],
                    label_b_to_a=gr["label_b_to_a"],
                )
                general_relationships.append({
                    "id": gr["id"],
                    "other_person": {"id": other_p["id"], "name": other_p["name"]},
                    "type": gr["type"],
                    "label": normalized["label_en"],
                    "directionality": gr["directionality"],
                    "notes": gr["notes"],
                })

    finally:
        connection.close()

    # 3. Perspective Relationship
    perspective_summary = None
    if perspective_id and perspective_id != person_id:
        from . import relationship
        perspective_summary = relationship.get_relationship(perspective_id, person_id)
    elif perspective_id == person_id:
        perspective_summary = {
            "perspective": {"id": person_id, "name": person_brief["name"]},
            "target": {"id": person_id, "name": person_brief["name"]},
            "primary": [{"en": "Self", "ur": "خود", "group": "primary"}],
            "additional": [],
        }

    # 4. Journal Preview
    from . import journals
    journal_data = journals.read_journal(person_id)

    return {
        "person": person_brief,
        "family": {
            "parents": parents,
            "spouses": spouses,
            "children": children,
            "siblings": siblings,
        },
        "general": general_relationships,
        "perspective": perspective_summary,
        "journal": journal_data,
    }


def delete_person(person_id: str, *, force: bool = False) -> dict:
    """Delete a person only when no structured relationships remain.

    Family history (parent-child, marriage, sibling facts) is never
    cascade-deleted: those people need an explicit manual data decision.
    Non-empty journals are safely moved to the archive directory before deletion.
    """
    record_pre_mutation_snapshot(f"Deleted person: {person_id}")

    connection = db.get_connection()
    try:
        row = connection.execute(
            "SELECT * FROM people WHERE id = ?", (person_id,)
        ).fetchone()
        if row is None:
            raise errors.NotFoundError(f"Unknown person id: {person_id}")
        folder = _folder_for(connection, person_id)
        blocking = []
        if connection.execute(
            "SELECT 1 FROM parent_child WHERE parent_id = ? OR child_id = ?",
            (person_id, person_id),
        ).fetchone():
            blocking.append("family parent/child facts")
        if connection.execute(
            "SELECT 1 FROM marriages WHERE spouse_a = ? OR spouse_b = ?",
            (person_id, person_id),
        ).fetchone():
            blocking.append("marriage facts")
        if connection.execute(
            "SELECT 1 FROM sibling_group_members WHERE person_id = ?",
            (person_id,),
        ).fetchone():
            blocking.append("sibling-group facts")
        if connection.execute(
            "SELECT 1 FROM general_relationships WHERE person_a = ? OR person_b = ?",
            (person_id, person_id),
        ).fetchone():
            blocking.append("general relationship records")
        if blocking and not force:
            raise errors.InvalidOperationError(
                f"Cannot delete {row['name']}: the person is referenced by "
                f"{', '.join(blocking)}.",
                code="PERSON_HAS_RELATIONSHIPS",
                details={"blocking": blocking},
            )
        if blocking:
            family_blocks = [
                item
                for item in blocking
                if item
                not in ("general relationship records", "provenance records")
            ]
            if family_blocks:
                raise errors.InvalidOperationError(
                    f"Cannot delete {row['name']}: the person is part of "
                    f"{', '.join(family_blocks)}. Remove those family facts first.",
                    code="PERSON_IN_FAMILY_GRAPH",
                    details={"blocking": family_blocks},
                )
        connection.execute("BEGIN")
        connection.execute(
            "DELETE FROM general_relationships WHERE person_a = ? OR person_b = ?",
            (person_id, person_id),
        )
        connection.execute(
            "DELETE FROM fact_sources WHERE entity_type = 'people' AND entity_key = ?",
            (person_id,),
        )
        connection.execute("DELETE FROM aliases WHERE person_id = ?", (person_id,))
        connection.execute("DELETE FROM person_groups WHERE person_id = ?", (person_id,))
        connection.execute("DELETE FROM people WHERE id = ?", (person_id,))
        connection.commit()
        archived_folder = None
        if folder is not None:
            resolved = folder.resolve()
            people_root = config.PEOPLE_DIR.resolve()
            if (
                people_root in resolved.parents
                and resolved.name == person_id
                and resolved.exists()
            ):
                # Archive journal directory before deleting folder
                archive_root = config.PEOPLE_DIR / "_archived"
                archive_root.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
                target_archive = archive_root / f"{person_id}_{stamp}"
                shutil.move(str(resolved), str(target_archive))
                archived_folder = str(target_archive)
                update_latest_filesystem_manifest({
                    "moves": [{"from": str(resolved), "to": str(target_archive)}]
                })
        return {
            "deleted": person_id,
            "name": row["name"],
            "folder_archived": archived_folder,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _folder_for(connection: sqlite3.Connection, person_id: str) -> Path | None:
    """Resolve the person's canonical folder without creating it."""
    return db.find_person_folder(connection, person_id)



def assign_group(person_id: str, group_id: str, *, primary: bool = False) -> dict:
    record_pre_mutation_snapshot(f"Assigned group {group_id} to person {person_id}")
    connection = db.get_connection()
    try:
        person = connection.execute(
            "SELECT id FROM people WHERE id = ?", (person_id,)
        ).fetchone()
        if person is None:
            raise errors.NotFoundError(f"Unknown person id: {person_id}")
        group = connection.execute(
            "SELECT id FROM groups WHERE id = ?", (group_id,)
        ).fetchone()
        if group is None:
            raise errors.NotFoundError(f"Unknown group id: {group_id}")
        old_folder = _folder_for(connection, person_id) if primary else None
        if primary and old_folder is not None:
            existing_primary = connection.execute(
                """
                SELECT g.slug FROM groups g
                JOIN person_groups pg ON pg.group_id = g.id
                WHERE pg.person_id = ? AND pg.is_primary = 1
                """,
                (person_id,),
            ).fetchone()
            if existing_primary and existing_primary["slug"] != group["slug"]:
                target = config.PEOPLE_DIR / group["slug"] / person_id
                if target.exists() and target != old_folder.resolve():
                    raise errors.InvalidOperationError(
                        "A person folder already exists under the target group. "
                        "Resolve the duplicate folders manually before moving.",
                        code="FOLDER_EXISTS",
                    )
        connection.execute("BEGIN")
        connection.execute(
            """
            INSERT OR IGNORE INTO person_groups (person_id, group_id, is_primary)
            VALUES (?, ?, ?)
            """,
            (person_id, group_id, 1 if primary else 0),
        )
        if primary:
            connection.execute(
                "UPDATE person_groups SET is_primary = 0 WHERE person_id = ?",
                (person_id,),
            )
            connection.execute(
                "UPDATE person_groups SET is_primary = 1 "
                "WHERE person_id = ? AND group_id = ?",
                (person_id, group_id),
            )
        connection.commit()
        if primary and old_folder is not None and old_folder.exists():
            target = config.PEOPLE_DIR / group["slug"] / person_id
            if target != old_folder and not target.exists():
                config.PEOPLE_DIR.joinpath(group["slug"]).mkdir(
                    parents=True, exist_ok=True
                )
                shutil.move(str(old_folder), str(target))
                update_latest_filesystem_manifest({
                    "moves": [{"from": str(old_folder), "to": str(target)}]
                })
        return get_person(person_id)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def remove_group(person_id: str, group_id: str) -> dict:
    record_pre_mutation_snapshot(f"Removed group {group_id} from person {person_id}")
    connection = db.get_connection()
    try:
        row = connection.execute(
            """
            SELECT is_primary FROM person_groups
            WHERE person_id = ? AND group_id = ?
            """,
            (person_id, group_id),
        ).fetchone()
        if row is None:
            raise errors.NotFoundError("That person is not in that group.")
        if row["is_primary"]:
            raise errors.InvalidOperationError(
                "Cannot remove the primary group without choosing another.",
                code="PRIMARY_GROUP_REQUIRED",
            )
        connection.execute("BEGIN")
        connection.execute(
            "DELETE FROM person_groups WHERE person_id = ? AND group_id = ?",
            (person_id, group_id),
        )
        connection.commit()
        return get_person(person_id)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
