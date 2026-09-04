"""Organisational group service.

Groups are organisational metadata only; they never define relationship
truth. A person may belong to many groups but has exactly one folder,
located under their primary group.
"""

import re

from .. import db
from . import errors

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,79}$")


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "group"


def _next_id(connection, base: str) -> str:
    candidate = base
    counter = 2
    while True:
        exists = connection.execute(
            "SELECT 1 FROM groups WHERE id = ? OR slug = ?", (candidate, candidate)
        ).fetchone()
        if exists is None:
            return candidate
        candidate = f"{base}_{counter}"
        counter += 1


def list_groups() -> list[dict]:
    connection = db.get_connection()
    try:
        rows = connection.execute(
            """
            SELECT g.*, (SELECT COUNT(*) FROM person_groups pg
                        WHERE pg.group_id = g.id) AS member_count
            FROM groups g
            ORDER BY g.display_order, g.name
            """
        ).fetchall()
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "slug": row["slug"],
                "kind": row["kind"],
                "display_order": row["display_order"],
                "member_count": row["member_count"],
            }
            for row in rows
        ]
    finally:
        connection.close()


def create_group(name: str) -> dict:
    if not name or not str(name).strip():
        raise errors.ValidationError("Group name is required.")
    connection = db.get_connection()
    try:
        connection.execute("BEGIN")
        base = _slugify(str(name).strip())
        group_id = _next_id(connection, base)
        max_order = connection.execute(
            "SELECT COALESCE(MAX(display_order), -1) AS m FROM groups"
        ).fetchone()["m"]
        connection.execute(
            """
            INSERT INTO groups (id, name, slug, kind, display_order)
            VALUES (?, ?, ?, 'custom', ?)
            """,
            (group_id, str(name).strip(), base, int(max_order) + 1),
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM groups WHERE id = ?", (group_id,)
        ).fetchone()
        return {
            "id": row["id"],
            "name": row["name"],
            "slug": row["slug"],
            "kind": row["kind"],
            "display_order": row["display_order"],
            "member_count": 0,
        }
    except sqlite3.IntegrityError as exc:
        connection.rollback()
        raise errors.ValidationError(
            f"A group named {name!r} already exists.", code="GROUP_EXISTS"
        ) from exc
    finally:
        connection.close()
