"""People directory and management service."""

import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .. import config, db
from ..domain.mutations.history import record_pre_mutation_snapshot, update_latest_filesystem_manifest
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
    folder = None
    try:
        folder = str(db.ensure_person_folder(connection, row["id"]))
    except (LookupError, OSError):
        folder = None
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
        "folder": folder,
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
        elif target_norm in p_name_norm or p_name_norm in target_norm:
            match_reason = "name substring match"
        elif target_aliases and (p_name_norm in target_aliases or target_norm in p_aliases):
            match_reason = "alias match"
        elif target_aliases and target_aliases.intersection(p_aliases):
            match_reason = "shared alias match"
        elif len(target_tokens) > 0 and (target_tokens.issubset(p_tokens) or p_tokens.issubset(target_tokens)):
            match_reason = "name token overlap"

        if match_reason:
            candidates.append({
                "id": p["id"],
                "name": p["name"],
                "aliases": p.get("aliases", []),
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
    from ..domain.mutations.history import update_latest_filesystem_manifest

    check_maintenance_lock()
    if DataRootManager.is_read_only():
        raise DataRootReadOnlyError()

    record_pre_mutation_snapshot(f"Created person: {name}")

    connection = db.get_connection()
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
        target_group = group_id or "other"
        group = connection.execute(
            "SELECT id FROM groups WHERE id = ?", (target_group,)
        ).fetchone()
        if group is None:
            raise errors.ValidationError(f"Unknown group id: {target_group}")
        connection.execute(
            """
            INSERT INTO person_groups (person_id, group_id, is_primary)
            VALUES (?, ?, 1)
            """,
            (person_id, group["id"]),
        )
        source_id = db.register_source(connection, origin=origin)
        db.link_fact_source(connection, source_id, "people", person_id, origin=origin)
        connection.commit()
        try:
            journal_path = db.ensure_journal(connection, person_id)
            update_latest_filesystem_manifest({"created_paths": [str(journal_path)]})
        except Exception:
            pass
        return get_person(person_id)
    except Exception:
        connection.rollback()
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
        if fields:
            connection.execute("BEGIN")
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
            source_id = db.register_source(connection, origin=origin)
            db.link_fact_source(
                connection, source_id, "people", person_id, origin=origin
            )
            connection.commit()
        return get_person(person_id)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


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
    row = connection.execute(
        """
        SELECT g.slug FROM groups g
        JOIN person_groups pg ON pg.group_id = g.id
        WHERE pg.person_id = ? AND pg.is_primary = 1
        """,
        (person_id,),
    ).fetchone()
    if row is None:
        return None
    folder = config.PEOPLE_DIR / row["slug"] / person_id
    return folder if folder.exists() else None


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
