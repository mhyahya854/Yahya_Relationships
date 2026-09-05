"""SQLite access for People Relationships.

``family.db`` remains the single structured store. This module applies the
legacy schema plus the application schema, tracks schema versions, and keeps
foreign keys enabled on every connection.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import config

DEFAULT_GROUPS = [
    ("family", "Family", "Family", "system"),
    ("close_friends", "Close Friends", "Close Friends", "system"),
    ("friends", "Friends", "Friends", "system"),
    ("colleagues", "Colleagues", "Colleagues", "system"),
    ("mentors", "Mentors", "Mentors", "system"),
    ("acquaintances", "Acquaintances", "Acquaintances", "system"),
    ("other", "Other", "Other", "system"),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class DatabaseOpenMode:
    OPEN_EXISTING = "OPEN_EXISTING"
    INITIALIZE_NEW = "INITIALIZE_NEW"


def get_connection(
    db_path: Path | None = None,
    *,
    mode: str = DatabaseOpenMode.OPEN_EXISTING,
    create: bool = False,
) -> sqlite3.Connection:
    """Open the canonical family.db connection.

    ``family.db`` is the single structured source of truth, so a missing file
    is an error, not an invitation for sqlite3 to silently create an empty
    database. Only explicit initialisation (mode=INITIALIZE_NEW or create=True)
    may create the file.
    """
    target = Path(db_path) if db_path is not None else config.DB_PATH
    should_create = create or (mode == DatabaseOpenMode.INITIALIZE_NEW)
    if not target.exists():
        if not should_create:
            from .data_root.errors import DataRootNotFoundError

            raise DataRootNotFoundError(
                f"Database file not found at '{target}'. Refusing to silently "
                "create an empty family.db; restore from backup or run "
                "initialize_database() to initialise it explicitly.",
                detail={"code": "MISSING_DATABASE", "path": str(target)},
            )
        target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(target))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def _apply_sql(connection: sqlite3.Connection, path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    connection.executescript(text)


def migrate(
    db_path: Path | None = None,
    *,
    mode: str = DatabaseOpenMode.OPEN_EXISTING,
    create: bool = False,
) -> None:
    """Apply legacy + application schema and seed organisational defaults.

    By default, only migrates an EXISTING database (mode=OPEN_EXISTING).
    If the database file does not exist, refuses to create a blank database
    unless explicit initialisation is requested (create=True or mode=INITIALIZE_NEW).
    """
    from .domain.family import engine as build_family

    connection = get_connection(db_path, mode=mode, create=create)
    try:
        connection.execute("BEGIN")
        build_family.create_sqlite_schema(connection)
        _apply_sql(connection, config.SCHEMA_PATH)
        _ensure_column(
            connection,
            "general_relationships",
            "direction_from",
            "ALTER TABLE general_relationships ADD COLUMN direction_from TEXT",
        )

        # Schema version bookkeeping.
        connection.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('app_schema_version', ?)",
            (str(config.APP_SCHEMA_VERSION),),
        )
        connection.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('app_name', ?)",
            (config.APP_NAME,),
        )
        connection.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('app_version', ?)",
            (config.APP_VERSION,),
        )
        connection.execute(f"PRAGMA user_version = {int(config.APP_SCHEMA_VERSION)}")

        # Seed organisational groups once.
        existing_groups = {
            row["name"] for row in connection.execute("SELECT name FROM groups")
        }
        for index, (group_id, name, slug, kind) in enumerate(DEFAULT_GROUPS):
            if name not in existing_groups:
                connection.execute(
                    """
                    INSERT INTO groups (id, name, slug, kind, display_order)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (group_id, name, slug, kind, index),
                )

        # One canonical folder per person: assign previously unassigned
        # people to the Family group as their primary group (Family is the
        # natural home of the existing legacy people).
        assigned = {
            row["person_id"]
            for row in connection.execute("SELECT person_id FROM person_groups")
        }
        family_row = connection.execute(
            "SELECT id FROM groups WHERE id = 'family'"
        ).fetchone()
        family_group_id = family_row["id"] if family_row else "family"
        people_ids = [
            row["id"]
            for row in connection.execute("SELECT id FROM people ORDER BY display_order")
        ]
        for person_id in people_ids:
            if person_id in assigned:
                continue
            connection.execute(
                """
                INSERT OR IGNORE INTO person_groups (person_id, group_id, is_primary)
                VALUES (?, ?, 1)
                """,
                (person_id, family_group_id),
            )

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database(db_path: Path | None = None) -> None:
    """Explicitly initialize a new database (INITIALIZE_NEW workflow)."""
    migrate(db_path, mode=DatabaseOpenMode.INITIALIZE_NEW, create=True)


def schema_info(connection: sqlite3.Connection) -> dict:
    row = connection.execute(
        "SELECT value FROM metadata WHERE key = 'app_schema_version'"
    ).fetchone()
    return {
        "schema_version": int(row["value"]) if row else 0,
        "user_version": connection.execute("PRAGMA user_version").fetchone()[0],
    }


def _ensure_column(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    alter_sql: str,
) -> None:
    columns = {
        row["name"]
        for row in connection.execute(f'PRAGMA table_info("{table}")')
    }
    if column not in columns:
        connection.execute(alter_sql)


def register_source(
    connection: sqlite3.Connection,
    *,
    origin: str,
    title: str | None = None,
    batch_number: str | None = None,
    source_path: str | None = None,
) -> int:
    """Return (creating if needed) a provenance source row."""
    batch = batch_number or f"U{datetime.now(timezone.utc):%Y%m%d%H%M%S}"
    path = source_path or f"user/{origin}/{batch}"
    display_title = title or f"Manual entry via app ({origin})"
    connection.execute(
        """
        INSERT OR IGNORE INTO sources (batch_number, file_path, title, kind)
        VALUES (?, ?, ?, 'evidence')
        """,
        (batch, path, display_title),
    )
    row = connection.execute(
        "SELECT id FROM sources WHERE file_path = ?", (path,)
    ).fetchone()
    if row is None:
        connection.execute(
            """
            INSERT OR IGNORE INTO sources (batch_number, file_path, title, kind)
            VALUES (?, ?, ?, 'evidence')
            """,
            (batch, path, display_title),
        )
        row = connection.execute(
            "SELECT id FROM sources WHERE file_path = ?", (path,)
        ).fetchone()
    return int(row["id"])


def link_fact_source(
    connection: sqlite3.Connection,
    source_id: int,
    entity_type: str,
    entity_key: str,
    *,
    origin: str = "user",
) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO fact_sources
          (source_id, entity_type, entity_key, note)
        VALUES (?, ?, ?, ?)
        """,
        (source_id, entity_type, entity_key, f"source_type={origin}"),
    )


def read_metadata(connection: sqlite3.Connection) -> dict:
    return {
        row["key"]: row["value"]
        for row in connection.execute("SELECT key, value FROM metadata")
    }


def metadata_to_json(connection: sqlite3.Connection) -> dict:
    """Metadata with JSON values decoded (used by the model loader)."""
    result = {}
    for row in connection.execute("SELECT key, value FROM metadata"):
        key, value = row["key"], row["value"]
        if key.startswith("_"):
            continue
        try:
            result[key] = json.loads(value)
        except (ValueError, TypeError):
            result[key] = value
    return result


def find_person_folder(
    connection: sqlite3.Connection, person_id: str
) -> Path | None:
    """Resolve the canonical person folder without modifying the filesystem.

    Checks the person's primary group first, then other group directories under
    people_dir, excluding `_archived` and hidden directories.
    Returns None if no folder exists. Never creates directories or files.
    """
    people_dir = config.PEOPLE_DIR
    if not people_dir.exists():
        return None

    # 1. Determine primary group slug to check primary location first
    group_row = connection.execute(
        """
        SELECT g.id, g.slug FROM groups g
        JOIN person_groups pg ON pg.group_id = g.id
        WHERE pg.person_id = ? AND pg.is_primary = 1
        """,
        (person_id,),
    ).fetchone()

    if group_row:
        slug = group_row["slug"]
        primary_dir = people_dir / slug
        if primary_dir.is_dir():
            candidate = primary_dir / person_id
            if candidate.is_dir():
                return candidate
        # Check case-insensitive match for primary group directory
        for sub in people_dir.iterdir():
            if sub.is_dir() and sub.name.lower() == slug.lower() and sub.name != "_archived":
                candidate = sub / person_id
                if candidate.is_dir():
                    return candidate

    # 2. Check other directories under people_dir (ignoring _archived and hidden dirs)
    for sub in people_dir.iterdir():
        if sub.is_dir() and sub.name != "_archived" and not sub.name.startswith("."):
            candidate = sub / person_id
            if candidate.is_dir():
                return candidate

    return None


def expected_person_folder(
    connection: sqlite3.Connection, person_id: str, group_id: str | None = None
) -> Path:
    """Return the expected canonical folder path for a person without touching the filesystem."""
    people_dir = config.PEOPLE_DIR
    group_row = None
    if group_id is not None:
        group_row = connection.execute(
            "SELECT id, slug FROM groups WHERE id = ? OR LOWER(id) = LOWER(?) OR LOWER(slug) = LOWER(?)",
            (group_id, group_id, group_id),
        ).fetchone()
    if group_row is None:
        group_row = connection.execute(
            """
            SELECT g.id, g.slug FROM groups g
            JOIN person_groups pg ON pg.group_id = g.id
            WHERE pg.person_id = ? AND pg.is_primary = 1
            """,
            (person_id,),
        ).fetchone()
    if group_row is None:
        group_row = connection.execute(
            "SELECT id, slug FROM groups WHERE id = 'other'"
        ).fetchone()
    slug = group_row["slug"] if group_row else "Other"

    target_group_dir = people_dir / slug
    if not target_group_dir.exists() and people_dir.exists():
        for sub in people_dir.iterdir():
            if sub.is_dir() and sub.name.lower() == slug.lower() and sub.name != "_archived":
                target_group_dir = sub
                break

    return target_group_dir / person_id


def find_journal_path(
    connection: sqlite3.Connection, person_id: str
) -> tuple[Path, bool]:
    """Return (canonical_journal_path, exists) without modifying the filesystem."""
    folder = find_person_folder(connection, person_id)
    if folder is not None:
        journal = folder / "journal.md"
        return journal, journal.is_file()
    expected = expected_person_folder(connection, person_id)
    return expected / "journal.md", False


def ensure_person_folder(
    connection: sqlite3.Connection, person_id: str, group_id: str | None = None
) -> Path:
    """Return the canonical person folder, creating it on disk if absent.

    MUTATING operation - for explicit creation, repair, or write paths only.
    """
    config.ensure_root_dirs()
    existing = find_person_folder(connection, person_id)
    if existing is not None:
        return existing

    folder = expected_person_folder(connection, person_id, group_id=group_id)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def ensure_journal(connection: sqlite3.Connection, person_id: str) -> Path:
    """Return the canonical journal.md path, creating the folder and file if absent.

    MUTATING operation - for explicit creation, repair, or write paths only.
    """
    person = connection.execute(
        "SELECT id, name FROM people WHERE id = ?", (person_id,)
    ).fetchone()
    if person is None:
        raise LookupError(f"Unknown person: {person_id}")
    folder = ensure_person_folder(connection, person_id)
    journal = folder / "journal.md"
    if not journal.exists():
        name = person["name"] if person["name"] else person_id
        journal.write_text(
            f"# {name}\n\n", encoding="utf-8", newline="\n"
        )
    return journal
