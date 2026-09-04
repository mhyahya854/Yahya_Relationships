"""Structured family fact writes.

Every mutation is validated against the legacy semantic rules (unknown ids,
duplicates, self-parent, ancestry cycles, single-person marriage, kind/role
values) and the model is re-validated and re-audited with the same code the
legacy builder uses. Derived kinship terms are never stored.
"""

import sqlite3

from .. import db
from ..domain.mutations.history import record_pre_mutation_snapshot
from ..model import _model_from_connection, run_family_audits, validate_model
from . import errors

PARENT_KINDS = {
    "biological",
    "unspecified",
    "adopted",
    "foster",
    "guardian",
    "step",
    "unknown",
}
PARENT_ROLES = {"mother", "father", "parent", "unknown"}
MARRIAGE_STATUSES = {"married", "divorced", "widowed", "unknown"}
CHILD_STATUSES = {"no_children", "unknown"}


def _begin(connection: sqlite3.Connection):
    connection.execute("BEGIN")


def _validate_after_write(connection: sqlite3.Connection) -> None:
    model = _model_from_connection(connection)
    try:
        validate_model(model)
        run_family_audits(model)
    except ValueError as exc:
        raise errors.ValidationError(str(exc), code="FAMILY_VALIDATION") from exc


def _require_person(connection: sqlite3.Connection, person_id: str, label: str):
    if connection.execute(
        "SELECT 1 FROM people WHERE id = ?", (person_id,)
    ).fetchone() is None:
        raise errors.NotFoundError(f"Unknown person ({label}): {person_id}")


def _check_write_allowed() -> None:
    from ..data_root.errors import DataRootReadOnlyError
    from ..data_root.manager import DataRootManager
    from ..domain.maintenance import check_maintenance_lock

    check_maintenance_lock()
    if DataRootManager.is_read_only():
        raise DataRootReadOnlyError()


def add_parent_child(
    *,
    parent_id: str,
    child_id: str,
    role: str = "parent",
    kind: str = "biological",
    origin: str = "user",
) -> dict:
    if kind not in PARENT_KINDS:
        raise errors.ValidationError(f"Unsupported parent-child kind: {kind!r}.")
    if role not in PARENT_ROLES:
        raise errors.ValidationError(f"Unsupported parent role: {role!r}.")

    _check_write_allowed()
    record_pre_mutation_snapshot(f"Added parent-child: {parent_id} -> {child_id} ({kind})")

    connection = db.get_connection()
    try:
        _require_person(connection, parent_id, "parent")
        _require_person(connection, child_id, "child")
        if parent_id == child_id:
            raise errors.ValidationError(
                "A person cannot be their own parent.", code="SELF_PARENT"
            )
        existing = connection.execute(
            "SELECT 1 FROM parent_child WHERE parent_id = ? AND child_id = ?",
            (parent_id, child_id),
        ).fetchone()
        if existing:
            raise errors.ValidationError(
                "That parent-child fact already exists.", code="DUPLICATE_FACT"
            )
        _begin(connection)
        connection.execute(
            """
            INSERT INTO parent_child (parent_id, child_id, role, kind)
            VALUES (?, ?, ?, ?)
            """,
            (parent_id, child_id, role, kind),
        )
        source_id = db.register_source(connection, origin=origin)
        db.link_fact_source(
            connection,
            source_id,
            "parent_child",
            f"{parent_id}|{child_id}",
            origin=origin,
        )
        _validate_after_write(connection)
        connection.commit()
        return {
            "ok": True,
            "parent_id": parent_id,
            "child_id": child_id,
            "role": role,
            "kind": kind,
        }
    except sqlite3.IntegrityError as exc:
        connection.rollback()
        raise errors.ValidationError(
            "That parent-child fact conflicts with existing constraints.",
            code="FACT_CONSTRAINT",
        ) from exc
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def delete_parent_child(parent_id: str, child_id: str) -> dict:
    _check_write_allowed()
    record_pre_mutation_snapshot(f"Deleted parent-child: {parent_id} -> {child_id}")
    connection = db.get_connection()
    try:
        existing = connection.execute(
            "SELECT 1 FROM parent_child WHERE parent_id = ? AND child_id = ?",
            (parent_id, child_id),
        ).fetchone()
        if not existing:
            raise errors.NotFoundError("Parent-child fact not found.")

        _begin(connection)
        connection.execute(
            "DELETE FROM parent_child WHERE parent_id = ? AND child_id = ?",
            (parent_id, child_id),
        )
        _validate_after_write(connection)
        connection.commit()
        return {"ok": True, "deleted": f"{parent_id}|{child_id}"}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def update_parent_child(parent_id: str, child_id: str, *, role: str | None = None, kind: str | None = None) -> dict:
    if kind is not None and kind not in PARENT_KINDS:
        raise errors.ValidationError(f"Unsupported parent-child kind: {kind!r}.")
    if role is not None and role not in PARENT_ROLES:
        raise errors.ValidationError(f"Unsupported parent role: {role!r}.")

    _check_write_allowed()
    record_pre_mutation_snapshot(f"Updated parent-child: {parent_id} -> {child_id}")
    connection = db.get_connection()
    try:
        existing = connection.execute(
            "SELECT role, kind FROM parent_child WHERE parent_id = ? AND child_id = ?",
            (parent_id, child_id),
        ).fetchone()
        if not existing:
            raise errors.NotFoundError("Parent-child fact not found.")

        new_role = role if role is not None else existing["role"]
        new_kind = kind if kind is not None else existing["kind"]

        _begin(connection)
        connection.execute(
            "UPDATE parent_child SET role = ?, kind = ? WHERE parent_id = ? AND child_id = ?",
            (new_role, new_kind, parent_id, child_id),
        )
        _validate_after_write(connection)
        connection.commit()
        return {"ok": True, "parent_id": parent_id, "child_id": child_id, "role": new_role, "kind": new_kind}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def add_marriage(
    *,
    person_a: str,
    person_b: str,
    status: str = "married",
    year: int | None = None,
    children_status: str | None = None,
    origin: str = "user",
) -> dict:
    if status not in MARRIAGE_STATUSES:
        raise errors.ValidationError(f"Unsupported marriage status: {status!r}.")
    if children_status not in (None, *CHILD_STATUSES):
        raise errors.ValidationError(
            f"Unsupported children status: {children_status!r}."
        )
    if year is not None and not 1800 <= int(year) <= 2100:
        raise errors.ValidationError("Marriage year must be between 1800 and 2100.")

    _check_write_allowed()
    record_pre_mutation_snapshot(f"Added marriage: {person_a} & {person_b}")

    connection = db.get_connection()
    try:
        _require_person(connection, person_a, "first spouse")
        _require_person(connection, person_b, "second spouse")
        if person_a == person_b:
            raise errors.ValidationError(
                "A person cannot marry themselves.", code="SELF_MARRIAGE"
            )
        spouse_a, spouse_b = sorted((person_a, person_b))
        existing = connection.execute(
            "SELECT 1 FROM marriages WHERE spouse_a = ? AND spouse_b = ?",
            (spouse_a, spouse_b),
        ).fetchone()
        if existing:
            raise errors.ValidationError(
                "That marriage is already recorded.", code="DUPLICATE_FACT"
            )
        max_order = connection.execute(
            "SELECT COALESCE(MAX(display_order), -1) AS m FROM marriages"
        ).fetchone()["m"]
        _begin(connection)
        connection.execute(
            """
            INSERT INTO marriages (
              spouse_a, spouse_b, status, year, children_status, display_order
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                spouse_a,
                spouse_b,
                status,
                year,
                children_status,
                int(max_order) + 1,
            ),
        )
        source_id = db.register_source(connection, origin=origin)
        db.link_fact_source(
            connection,
            source_id,
            "marriages",
            f"{spouse_a}|{spouse_b}",
            origin=origin,
        )
        _validate_after_write(connection)
        connection.commit()
        return {
            "ok": True,
            "person_a": spouse_a,
            "person_b": spouse_b,
            "status": status,
            "year": year,
            "children_status": children_status,
        }
    except sqlite3.IntegrityError as exc:
        connection.rollback()
        raise errors.ValidationError(
            "That marriage conflicts with existing constraints.",
            code="FACT_CONSTRAINT",
        ) from exc
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def delete_marriage(person_a: str, person_b: str) -> dict:
    spouse_a, spouse_b = sorted((person_a, person_b))
    _check_write_allowed()
    record_pre_mutation_snapshot(f"Deleted marriage: {spouse_a} & {spouse_b}")
    connection = db.get_connection()
    try:
        existing = connection.execute(
            "SELECT 1 FROM marriages WHERE spouse_a = ? AND spouse_b = ?",
            (spouse_a, spouse_b),
        ).fetchone()
        if not existing:
            raise errors.NotFoundError("Marriage fact not found.")

        _begin(connection)
        connection.execute(
            "DELETE FROM marriages WHERE spouse_a = ? AND spouse_b = ?",
            (spouse_a, spouse_b),
        )
        _validate_after_write(connection)
        connection.commit()
        return {"ok": True, "deleted": f"{spouse_a}|{spouse_b}"}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def update_marriage(
    person_a: str,
    person_b: str,
    *,
    status: str | None = None,
    year: int | None = None,
    children_status: str | None = None,
) -> dict:
    spouse_a, spouse_b = sorted((person_a, person_b))
    if status is not None and status not in MARRIAGE_STATUSES:
        raise errors.ValidationError(f"Unsupported marriage status: {status!r}.")
    if children_status not in (None, *CHILD_STATUSES):
        raise errors.ValidationError(f"Unsupported children status: {children_status!r}.")
    if year is not None and not 1800 <= int(year) <= 2100:
        raise errors.ValidationError("Marriage year must be between 1800 and 2100.")

    _check_write_allowed()
    record_pre_mutation_snapshot(f"Updated marriage: {spouse_a} & {spouse_b}")
    connection = db.get_connection()
    try:
        row = connection.execute(
            "SELECT * FROM marriages WHERE spouse_a = ? AND spouse_b = ?",
            (spouse_a, spouse_b),
        ).fetchone()
        if not row:
            raise errors.NotFoundError("Marriage fact not found.")

        new_status = status if status is not None else row["status"]
        new_year = year if year is not None else row["year"]
        new_children_status = children_status if children_status is not None else row["children_status"]

        _begin(connection)
        connection.execute(
            """
            UPDATE marriages
            SET status = ?, year = ?, children_status = ?
            WHERE spouse_a = ? AND spouse_b = ?
            """,
            (new_status, new_year, new_children_status, spouse_a, spouse_b),
        )
        _validate_after_write(connection)
        connection.commit()
        return {
            "ok": True,
            "person_a": spouse_a,
            "person_b": spouse_b,
            "status": new_status,
            "year": new_year,
            "children_status": new_children_status,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def add_sibling_group(
    *,
    member_ids: list[str],
    type_: str | None = None,
    ordered: bool = False,
    origin: str = "user",
) -> dict:
    members = [member for member in member_ids if member]
    if len(members) < 2:
        raise errors.ValidationError(
            "A sibling group needs at least two members.", code="SIBLING_GROUP_SIZE"
        )
    if len(set(members)) != len(members):
        raise errors.ValidationError(
            "A sibling group cannot repeat a person.", code="SIBLING_GROUP_REPEAT"
        )
    if type_ not in (None, "full"):
        raise errors.ValidationError(
            f"Unsupported sibling-group type: {type_!r}."
        )
    if type_ == "full" and len(members) != 2:
        raise errors.ValidationError(
            "Full-sibling facts need exactly two members.",
            code="FULL_SIBLING_SIZE",
        )

    _check_write_allowed()
    record_pre_mutation_snapshot(f"Added sibling group: {', '.join(members)}")

    connection = db.get_connection()
    try:
        for member in members:
            _require_person(connection, member, "sibling group member")
        for group in connection.execute("SELECT id FROM sibling_groups").fetchall():
            stored = [
                row["person_id"]
                for row in connection.execute(
                    """
                    SELECT person_id FROM sibling_group_members
                    WHERE group_id = ? ORDER BY member_order, person_id
                    """,
                    (group["id"],),
                )
            ]
            if sorted(stored) == sorted(members):
                raise errors.ValidationError(
                    "That sibling group already exists.", code="DUPLICATE_FACT"
                )
        max_order = connection.execute(
            "SELECT COALESCE(MAX(display_order), -1) AS m FROM sibling_groups"
        ).fetchone()["m"]
        group_id = f"sib_{'_'.join(members)}"
        counter = 2
        while connection.execute(
            "SELECT 1 FROM sibling_groups WHERE id = ?", (group_id,)
        ).fetchone():
            group_id = f"sib_{'_'.join(members)}_{counter}"
            counter += 1
        _begin(connection)
        connection.execute(
            """
            INSERT INTO sibling_groups (id, is_ordered, type, display_order)
            VALUES (?, ?, ?, ?)
            """,
            (group_id, 1 if ordered else 0, type_, int(max_order) + 1),
        )
        for index, member in enumerate(members, start=1):
            connection.execute(
                """
                INSERT INTO sibling_group_members
                  (group_id, person_id, member_order)
                VALUES (?, ?, ?)
                """,
                (group_id, member, index if ordered else None),
            )
        source_id = db.register_source(connection, origin=origin)
        db.link_fact_source(
            connection, source_id, "sibling_groups", group_id, origin=origin
        )
        _validate_after_write(connection)
        connection.commit()
        return {"ok": True, "id": group_id, "members": members}
    except sqlite3.IntegrityError as exc:
        connection.rollback()
        raise errors.ValidationError(
            "That sibling group conflicts with existing constraints.",
            code="FACT_CONSTRAINT",
        ) from exc
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def delete_sibling_group(group_id: str) -> dict:
    _check_write_allowed()
    record_pre_mutation_snapshot(f"Deleted sibling group: {group_id}")
    connection = db.get_connection()
    try:
        existing = connection.execute(
            "SELECT 1 FROM sibling_groups WHERE id = ?", (group_id,)
        ).fetchone()
        if not existing:
            raise errors.NotFoundError("Sibling group fact not found.")

        _begin(connection)
        connection.execute("DELETE FROM sibling_group_members WHERE group_id = ?", (group_id,))
        connection.execute("DELETE FROM sibling_groups WHERE id = ?", (group_id,))
        _validate_after_write(connection)
        connection.commit()
        return {"ok": True, "deleted": group_id}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def family_facts(connection=None) -> dict:
    """Objective structured family facts (not derived labels)."""
    own = connection is None
    connection = connection or db.get_connection()
    try:
        people = [
            dict(row)
            for row in connection.execute(
                "SELECT id, name, gender, birth_year FROM people ORDER BY display_order"
            )
        ]
        parent_child = [
            dict(row)
            for row in connection.execute(
                """
                SELECT id, parent_id, child_id, role, kind
                FROM parent_child ORDER BY id
                """
            )
        ]
        marriages = [
            dict(row)
            for row in connection.execute(
                """
                SELECT id, spouse_a, spouse_b, status, year, children_status
                FROM marriages ORDER BY display_order, id
                """
            )
        ]
        sibling_groups = [
            {
                "id": row["id"],
                "type": row["type"],
                "ordered": bool(row["is_ordered"]),
                "members": [
                    member["person_id"]
                    for member in connection.execute(
                        """
                        SELECT person_id FROM sibling_group_members
                        WHERE group_id = ? ORDER BY member_order, person_id
                        """,
                        (row["id"],),
                    )
                ],
            }
            for row in connection.execute(
                """
                SELECT id, type, is_ordered FROM sibling_groups
                ORDER BY display_order, id
                """
            )
        ]
        return {
            "people": people,
            "parent_child": parent_child,
            "marriages": marriages,
            "sibling_groups": sibling_groups,
        }
    finally:
        if own:
            connection.close()
