"""Explicit general (non-family) relationships.

General relationships are stored separately from family derivation facts and
are never inferred transitively.
"""

import sqlite3

from .. import db
from ..domain.mutations.history import pop_latest_snapshot, record_pre_mutation_snapshot
from . import errors

SYMMETRIC_TYPES = {
    "close_friend",
    "friend",
    "childhood_friend",
    "best_friend",
    "colleague",
    "former_colleague",
    "neighbour",
    "acquaintance",
}


def _normalize_pair(person_a: str, person_b: str) -> tuple[str, str]:
    return (person_a, person_b) if person_a <= person_b else (person_b, person_a)


def list_general_relationships(person_id: str | None = None) -> list[dict]:
    connection = db.get_connection()
    try:
        sql = "SELECT * FROM general_relationships"
        params: list = []
        if person_id:
            sql += " WHERE person_a = ? OR person_b = ?"
            params.extend([person_id, person_id])
        sql += " ORDER BY id"
        rows = connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def _check_write_allowed() -> None:
    from ..data_root.errors import DataRootReadOnlyError
    from ..data_root.manager import DataRootManager
    from ..domain.maintenance import check_maintenance_lock

    check_maintenance_lock()
    if DataRootManager.is_read_only():
        raise DataRootReadOnlyError()


def add_general_relationship(
    *,
    person_a: str,
    person_b: str,
    type: str,
    directionality: str = "symmetric",
    label_a_to_b: str | None = None,
    label_b_to_a: str | None = None,
    notes: str | None = None,
) -> dict:
    if directionality not in ("symmetric", "directional"):
        raise errors.ValidationError(
            f"Unsupported directionality: {directionality!r}."
        )
    if not type or not str(type).strip():
        raise errors.ValidationError("A relationship type is required.")
    if person_a == person_b:
        raise errors.ValidationError(
            "A person cannot have a general relationship with themselves.",
            code="SELF_RELATIONSHIP",
        )
    _check_write_allowed()
    record_pre_mutation_snapshot(f"Added general relationship ({type}) between {person_a} and {person_b}")
    connection = db.get_connection()
    try:
        for pid, label in ((person_a, "first person"), (person_b, "second person")):
            if connection.execute(
                "SELECT 1 FROM people WHERE id = ?", (pid,)
            ).fetchone() is None:
                raise errors.NotFoundError(f"Unknown person ({label}): {pid}")
        if directionality == "symmetric":
            label_a_to_b = label_a_to_b or _default_label(type)
            label_b_to_a = label_a_to_b
            direction_from = None
        else:
            if not label_a_to_b or not label_b_to_a:
                raise errors.ValidationError(
                    "Directional relationships need both a_to_b and b_to_a labels."
                )
            direction_from = person_a
        person_low, person_high = _normalize_pair(person_a, person_b)
        if person_low == person_high:
            raise errors.ValidationError(
                "A person cannot have a relationship with themselves.",
                code="SELF_RELATIONSHIP",
            )
        rel_type = str(type).strip()
        if rel_type == "custom":
            existing = connection.execute(
                """
                SELECT id FROM general_relationships
                WHERE person_a = ? AND person_b = ? AND type = 'custom' AND directionality = ?
                AND ((direction_from IS NULL AND ? IS NULL) OR direction_from = ?)
                AND COALESCE(label_a_to_b, '') = COALESCE(?, '')
                AND COALESCE(label_b_to_a, '') = COALESCE(?, '')
                """,
                (person_low, person_high, directionality, direction_from, direction_from, label_a_to_b, label_b_to_a),
            ).fetchone()
        else:
            existing = connection.execute(
                """
                SELECT id FROM general_relationships
                WHERE person_a = ? AND person_b = ? AND type = ? AND directionality = ?
                AND ((direction_from IS NULL AND ? IS NULL) OR direction_from = ?)
                """,
                (person_low, person_high, rel_type, directionality, direction_from, direction_from),
            ).fetchone()
        if existing:
            raise errors.ValidationError(
                "That exact general relationship already exists between those people.",
                code="DUPLICATE_FACT",
            )
        connection.execute("BEGIN")
        now = db.utc_now()
        cursor = connection.execute(
            """
            INSERT INTO general_relationships (
              person_a, person_b, type, directionality,
              direction_from, label_a_to_b, label_b_to_a,
              notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                person_low,
                person_high,
                rel_type,
                directionality,
                direction_from,
                label_a_to_b,
                label_b_to_a,
                notes,
                now,
                now,
            ),
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM general_relationships WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        return dict(row)
    except sqlite3.IntegrityError as exc:
        connection.rollback()
        pop_latest_snapshot()
        raise errors.ValidationError(
            "That relationship conflicts with existing constraints.",
            code="FACT_CONSTRAINT",
        ) from exc
    except Exception:
        connection.rollback()
        pop_latest_snapshot()
        raise
    finally:
        connection.close()


def update_general_relationship(
    relationship_id: int,
    *,
    type: str | None = None,
    directionality: str | None = None,
    direction_from: str | None = None,
    label_a_to_b: str | None = None,
    label_b_to_a: str | None = None,
    notes: str | None = None,
) -> dict:
    _check_write_allowed()
    record_pre_mutation_snapshot(f"Updated general relationship ID #{relationship_id}")
    connection = db.get_connection()
    try:
        row = connection.execute(
            "SELECT * FROM general_relationships WHERE id = ?", (relationship_id,)
        ).fetchone()
        if row is None:
            raise errors.NotFoundError(
                f"Unknown general relationship id: {relationship_id}"
            )

        person_a = row["person_a"]
        person_b = row["person_b"]

        new_type = str(type).strip() if type is not None else row["type"]
        if not new_type:
            raise errors.ValidationError("A relationship type is required.")

        new_directionality = str(directionality).strip() if directionality is not None else row["directionality"]
        if new_directionality not in ("symmetric", "directional"):
            raise errors.ValidationError(f"Invalid directionality: {new_directionality!r}.")

        if new_directionality == "symmetric":
            new_direction_from = None
        else:
            if direction_from is not None:
                new_direction_from = direction_from
            else:
                new_direction_from = row["direction_from"] or person_a
            if new_direction_from not in (person_a, person_b):
                raise errors.ValidationError(
                    f"direction_from must be either {person_a} or {person_b}."
                )

        new_label_a_to_b = label_a_to_b if label_a_to_b is not None else row["label_a_to_b"]
        new_label_b_to_a = label_b_to_a if label_b_to_a is not None else row["label_b_to_a"]
        new_notes = notes if notes is not None else row["notes"]

        # Duplicate collision check against other records (id != relationship_id)
        if new_type == "custom":
            existing = connection.execute(
                """
                SELECT id FROM general_relationships
                WHERE id != ? AND person_a = ? AND person_b = ? AND type = 'custom' AND directionality = ?
                AND ((direction_from IS NULL AND ? IS NULL) OR direction_from = ?)
                AND COALESCE(label_a_to_b, '') = COALESCE(?, '')
                AND COALESCE(label_b_to_a, '') = COALESCE(?, '')
                """,
                (relationship_id, person_a, person_b, new_directionality, new_direction_from, new_direction_from, new_label_a_to_b, new_label_b_to_a),
            ).fetchone()
        else:
            existing = connection.execute(
                """
                SELECT id FROM general_relationships
                WHERE id != ? AND person_a = ? AND person_b = ? AND type = ? AND directionality = ?
                AND ((direction_from IS NULL AND ? IS NULL) OR direction_from = ?)
                """,
                (relationship_id, person_a, person_b, new_type, new_directionality, new_direction_from, new_direction_from),
            ).fetchone()

        if existing:
            raise errors.ValidationError(
                "That exact general relationship already exists between those people.",
                code="DUPLICATE_FACT",
            )

        connection.execute("BEGIN")
        now = db.utc_now()
        connection.execute(
            """
            UPDATE general_relationships
            SET type = ?, directionality = ?, direction_from = ?,
                label_a_to_b = ?, label_b_to_a = ?, notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                new_type,
                new_directionality,
                new_direction_from,
                new_label_a_to_b,
                new_label_b_to_a,
                new_notes,
                now,
                relationship_id,
            ),
        )
        connection.commit()
        updated_row = connection.execute(
            "SELECT * FROM general_relationships WHERE id = ?", (relationship_id,)
        ).fetchone()
        return dict(updated_row)
    except sqlite3.IntegrityError as exc:
        connection.rollback()
        pop_latest_snapshot()
        raise errors.ValidationError(
            "That relationship conflicts with existing constraints.",
            code="FACT_CONSTRAINT",
        ) from exc
    except Exception:
        connection.rollback()
        pop_latest_snapshot()
        raise
    finally:
        connection.close()


def delete_general_relationship(relationship_id: int) -> dict:
    _check_write_allowed()
    record_pre_mutation_snapshot(f"Deleted general relationship ID #{relationship_id}")
    connection = db.get_connection()
    try:
        row = connection.execute(
            "SELECT id FROM general_relationships WHERE id = ?", (relationship_id,)
        ).fetchone()
        if row is None:
            raise errors.NotFoundError(
                f"Unknown general relationship id: {relationship_id}"
            )
        connection.execute("BEGIN")
        connection.execute(
            "DELETE FROM general_relationships WHERE id = ?", (relationship_id,)
        )
        connection.commit()
        return {"ok": True, "deleted_id": relationship_id}
    except Exception:
        connection.rollback()
        pop_latest_snapshot()
        raise
    finally:
        connection.close()


def _default_label(type: str) -> str:
    labels = {
        "close_friend": "Close friend",
        "friend": "Friend",
        "childhood_friend": "Childhood friend",
        "best_friend": "Best friend",
        "colleague": "Colleague",
        "former_colleague": "Former colleague",
        "mentor": "Mentor",
        "mentee": "Mentee",
        "neighbour": "Neighbour",
        "acquaintance": "Acquaintance",
    }
    return labels.get(type, type.replace("_", " ").title())
