"""SQLite access for Mosaic's active legacy or canonical structured store."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .data_root.manager import DataRootManager

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
    """Open the active SQLite connection without silent creation or fallback.

    The resolved active database is the single structured source of truth, so
    a missing file is an error, not an invitation for sqlite3 to silently
    create an empty database. Only explicit initialisation
    (mode=INITIALIZE_NEW or create=True) may create the file.
    """
    target = Path(db_path) if db_path is not None else config.DB_PATH
    should_create = create or (mode == DatabaseOpenMode.INITIALIZE_NEW)
    if db_path is None and DataRootManager.has_incomplete_operation():
        from .data_root.errors import DataRootInvalidError

        raise DataRootInvalidError(
            "The Data Root contains an incomplete migration or restore marker. "
            "Runtime database access is blocked until recovery completes.",
            detail={"code": "DATA_ROOT_OPERATION_INCOMPLETE"},
        )
    if not target.exists():
        if not should_create:
            from .data_root.errors import DataRootNotFoundError

            raise DataRootNotFoundError(
                f"Database file not found at '{target}'. Refusing to silently "
                "create an empty database; restore from backup or run "
                "initialize_database() to initialise it explicitly.",
                detail={"code": "MISSING_DATABASE", "path": str(target)},
            )
        target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(target))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    if target.exists() and not should_create and target.name == config.CANONICAL_DB_NAME:
        try:
            schema_version = get_current_schema_version(connection)
            if schema_version != config.CANONICAL_SCHEMA_VERSION:
                raise SchemaVersionMismatchError(
                    f"Canonical database must be schema {config.CANONICAL_SCHEMA_VERSION}; "
                    f"found schema {schema_version}."
                )
        except Exception:
            connection.close()
            raise
    return connection


def _apply_sql(connection: sqlite3.Connection, path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    connection.executescript(text)


_MIGRATION_FAILPOINT: str | None = None


def _check_migration_failpoint(name: str) -> None:
    if _MIGRATION_FAILPOINT == name:
        raise RuntimeError(f"Injected migration failure at failpoint: {name}")


class SchemaVersionMismatchError(Exception):
    """Raised when metadata app_schema_version and PRAGMA user_version disagree."""
    pass


def get_current_schema_version(connection: sqlite3.Connection) -> int:
    """Read the current schema version using metadata and PRAGMA user_version authorities."""
    meta_table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='metadata'"
    ).fetchone()
    meta_ver = None
    if meta_table:
        row = connection.execute(
            "SELECT value FROM metadata WHERE key = 'app_schema_version'"
        ).fetchone()
        if row and row["value"] is not None and str(row["value"]).strip().isdigit():
            meta_ver = int(row["value"])

    user_ver = connection.execute("PRAGMA user_version").fetchone()[0]

    # If both authorities report non-zero versions and they disagree, refuse to guess destructively
    if meta_ver is not None and user_ver != 0 and meta_ver != user_ver:
        raise SchemaVersionMismatchError(
            f"Database schema version mismatch: metadata app_schema_version={meta_ver} "
            f"disagrees with PRAGMA user_version={user_ver}."
        )

    if meta_ver is not None:
        return meta_ver
    if user_ver != 0:
        return user_ver
    # Legacy DB before version tracking
    return 1


def is_canonical_connection(connection: sqlite3.Connection) -> bool:
    """Return True if this connection targets the canonical database (Schema 3 / relationships.db)."""
    try:
        ver = connection.execute("PRAGMA user_version").fetchone()[0]
        if ver >= 3:
            return True
        for row in connection.execute("PRAGMA database_list").fetchall():
            db_file = row[2]
            if db_file and Path(db_file).name == config.CANONICAL_DB_NAME:
                return True
    except Exception:
        pass
    return False


def _seed_groups_and_assignments(connection: sqlite3.Connection) -> None:
    """Seed organisational groups and default family primary assignment."""
    existing_groups = {
        row[0] for row in connection.execute("SELECT name FROM groups")
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

    assigned = {
        row[0]
        for row in connection.execute("SELECT person_id FROM person_groups")
    }
    family_row = connection.execute(
        "SELECT id FROM groups WHERE id = 'family'"
    ).fetchone()
    family_group_id = family_row[0] if family_row else "family"
    people_ids = [
        row[0]
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


def _bootstrap_new_database(connection: sqlite3.Connection, target_schema: int = 2) -> None:
    """Initialize a brand-new empty database directly into target schema (v2 for family.db, v3 for relationships.db)."""
    from .domain.family import engine as build_family

    build_family.create_sqlite_schema(connection)
    _apply_sql(connection, config.SCHEMA_PATH)

    connection.isolation_level = None
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('app_schema_version', ?)",
            (str(target_schema),),
        )
        connection.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('app_name', ?)",
            (config.APP_NAME,),
        )
        connection.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('app_version', ?)",
            (config.APP_VERSION,),
        )
        connection.execute(f"PRAGMA user_version = {int(target_schema)}")

        _seed_groups_and_assignments(connection)
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise


def _migrate_v1_to_v2_atomic(connection: sqlite3.Connection) -> None:
    """Migrate an existing schema v1 database to v2 in a single atomic transaction.

    Never relies on executescript() inside the transaction.
    Supports controlled failpoints to prove failure atomicity.
    """
    connection.isolation_level = None
    connection.execute("BEGIN IMMEDIATE")
    try:
        # Ensure organizational tables exist
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS groups (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL UNIQUE,
              slug TEXT NOT NULL UNIQUE,
              kind TEXT NOT NULL DEFAULT 'custom'
                CHECK (kind IN ('system', 'custom')),
              display_order INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS person_groups (
              person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
              group_id TEXT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
              is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
              PRIMARY KEY (person_id, group_id)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_person_groups_group ON person_groups(group_id)"
        )

        has_general_rel = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='general_relationships'"
        ).fetchone()

        if has_general_rel:
            cols = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(general_relationships)")
            }
            if "direction_from" not in cols:
                connection.execute(
                    "ALTER TABLE general_relationships ADD COLUMN direction_from TEXT"
                )

            _check_migration_failpoint("before_create_v2_table")

            connection.execute(
                """
                CREATE TABLE general_relationships_v2 (
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
                )
                """
            )

            _check_migration_failpoint("after_create_v2_table")

            connection.execute(
                """
                INSERT INTO general_relationships_v2 (
                  id, person_a, person_b, type, directionality, direction_from,
                  label_a_to_b, label_b_to_a, notes, created_at, updated_at
                )
                SELECT id, person_a, person_b, type,
                       COALESCE(directionality, 'symmetric'),
                       direction_from,
                       label_a_to_b, label_b_to_a, notes, created_at, updated_at
                FROM general_relationships
                """
            )

            _check_migration_failpoint("after_copy_rows")

            connection.execute("DROP TABLE general_relationships")

            _check_migration_failpoint("after_drop_old_table")

            connection.execute(
                "ALTER TABLE general_relationships_v2 RENAME TO general_relationships"
            )
        else:
            connection.execute(
                """
                CREATE TABLE general_relationships (
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
                )
                """
            )

        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_general_relationships_person ON general_relationships(person_a, person_b)"
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_general_rel_symmetric_standard
              ON general_relationships(person_a, person_b, type)
              WHERE directionality = 'symmetric' AND type <> 'custom'
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_general_rel_symmetric_custom
              ON general_relationships(person_a, person_b, COALESCE(label_a_to_b, ''), COALESCE(label_b_to_a, ''))
              WHERE directionality = 'symmetric' AND type = 'custom'
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_general_rel_directional_standard
              ON general_relationships(person_a, person_b, type, direction_from)
              WHERE directionality = 'directional' AND type <> 'custom'
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_general_rel_directional_custom
              ON general_relationships(person_a, person_b, direction_from, COALESCE(label_a_to_b, ''), COALESCE(label_b_to_a, ''))
              WHERE directionality = 'directional' AND type = 'custom'
            """
        )

        _check_migration_failpoint("during_unique_index")
        _check_migration_failpoint("before_metadata_version_update")

        # Schema version bookkeeping
        connection.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('app_schema_version', '2')",
        )
        connection.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('app_name', ?)",
            (config.APP_NAME,),
        )
        connection.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('app_version', ?)",
            (config.APP_VERSION,),
        )
        connection.execute("PRAGMA user_version = 2")

        _seed_groups_and_assignments(connection)

        fk_violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if fk_violations:
            raise RuntimeError(f"Foreign key violation after v1->v2 migration: {fk_violations}")

        _check_migration_failpoint("after_version_bookkeeping")

        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise


def _migrate_v2_to_v3_atomic(connection: sqlite3.Connection) -> None:
    """Migrate an existing schema v2 database to v3 in a single atomic transaction."""
    connection.isolation_level = None
    connection.execute("BEGIN IMMEDIATE")
    try:
        _ensure_column(
            connection,
            "people",
            "category",
            "ALTER TABLE people ADD COLUMN category TEXT NOT NULL DEFAULT 'Family' CHECK (category IN ('Me', 'Family', 'Friends'))",
        )
        _ensure_column(
            connection,
            "people",
            "created_at",
            "ALTER TABLE people ADD COLUMN created_at TEXT",
        )
        _ensure_column(
            connection,
            "people",
            "updated_at",
            "ALTER TABLE people ADD COLUMN updated_at TEXT",
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS unresolved_people (
              id TEXT PRIMARY KEY,
              label TEXT,
              notes TEXT,
              created_at TEXT NOT NULL,
              resolved_to_person_id TEXT REFERENCES people(id),
              resolved_at TEXT
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS identifier_aliases (
              id INTEGER PRIMARY KEY,
              old_identifier TEXT NOT NULL UNIQUE,
              canonical_id TEXT NOT NULL REFERENCES people(id) ON DELETE RESTRICT,
              entity_type TEXT NOT NULL DEFAULT 'person' CHECK (entity_type = 'person'),
              notes TEXT,
              created_at TEXT NOT NULL,
              CHECK (old_identifier <> canonical_id)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_identifier_aliases_canonical ON identifier_aliases(canonical_id)"
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS platform_identities (
              id INTEGER PRIMARY KEY,
              person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
              platform TEXT NOT NULL,
              identity_value TEXT NOT NULL,
              is_current INTEGER NOT NULL DEFAULT 1 CHECK (is_current IN (0, 1)),
              notes TEXT,
              created_at TEXT
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_platform_identities_person ON platform_identities(person_id)"
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS places (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              address TEXT,
              latitude REAL,
              longitude REAL,
              place_type TEXT,
              notes TEXT,
              created_at TEXT
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
              id TEXT PRIMARY KEY,
              title TEXT NOT NULL,
              date_exact TEXT,
              date_approx TEXT,
              place_id TEXT REFERENCES places(id),
              event_type TEXT,
              notes TEXT,
              created_at TEXT
            )
            """
        )

        connection.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('app_schema_version', ?)",
            (str(config.CANONICAL_SCHEMA_VERSION),),
        )
        connection.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('app_name', ?)",
            (config.APP_NAME,),
        )
        connection.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('app_version', ?)",
            (config.APP_VERSION,),
        )
        connection.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('_source_of_truth', 'relationships.db')"
        )
        connection.execute(f"PRAGMA user_version = {int(config.CANONICAL_SCHEMA_VERSION)}")

        fk_violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if fk_violations:
            raise RuntimeError(f"Foreign key violation after v2->v3 migration: {fk_violations}")

        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise


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
    connection = get_connection(db_path, mode=mode, create=create)
    try:
        table_count = connection.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]

        resolved_db = db_path if db_path else DataRootManager.get_database_path()
        target_ver = 3 if resolved_db.name == "relationships.db" else 2

        if table_count == 0:
            _bootstrap_new_database(connection, target_schema=target_ver)
            if target_ver == 3:
                _migrate_v2_to_v3_atomic(connection)
            return

        # EXISTING DATABASE:
        # Pre-validation: detect schema-version mismatch BEFORE any mutation
        current_ver = get_current_schema_version(connection)

        if current_ver >= target_ver:
            # Idempotent: already at target version, no destructive work
            return

        if current_ver < 2:
            _migrate_v1_to_v2_atomic(connection)
            current_ver = 2

        if current_ver < target_ver and target_ver == 3:
            _migrate_v2_to_v3_atomic(connection)
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
        row[1]
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


def resolve_canonical_id(connection: sqlite3.Connection, identifier: str) -> str:
    """Resolve an identifier (historical or canonical) to its authoritative canonical person ID."""
    if not identifier:
        return identifier
    # Check if identifier directly matches a person in people table
    row = connection.execute("SELECT id FROM people WHERE id = ?", (identifier,)).fetchone()
    if row:
        return str(row["id"])
    # Check identifier_aliases table if it exists
    has_alias_table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='identifier_aliases'"
    ).fetchone()
    if has_alias_table:
        alias_row = connection.execute(
            "SELECT canonical_id FROM identifier_aliases WHERE old_identifier = ? AND entity_type = 'person'",
            (identifier,),
        ).fetchone()
        if alias_row:
            return str(alias_row["canonical_id"])
    return identifier


def find_person_folder(
    connection: sqlite3.Connection, person_id: str, root: Path | None = None
) -> Path | None:
    """Resolve the canonical person folder without modifying the filesystem.

    Checks top-level People/, category directories (Me, Family, Friends),
    primary group directories, and legacy layouts.
    Returns None if no folder exists. Never creates directories or files.
    """
    resolved_id = resolve_canonical_id(connection, person_id)
    candidate_ids = [resolved_id] if resolved_id == person_id else [resolved_id, person_id]

    people_dir = DataRootManager.get_people_dir(root) if root else config.PEOPLE_DIR
    if not people_dir.exists():
        return None

    # 1. Check top-level under people_dir (e.g. unknown_person--UP####)
    for cid in candidate_ids:
        candidate = people_dir / cid
        if candidate.is_dir():
            return candidate

    # 2. Check canonical category if available in people table
    has_cat = connection.execute(
        "SELECT 1 FROM pragma_table_info('people') WHERE name = 'category'"
    ).fetchone()
    if has_cat:
        for cid in candidate_ids:
            cat_row = connection.execute(
                "SELECT category FROM people WHERE id = ?", (cid,)
            ).fetchone()
            if cat_row and cat_row["category"]:
                cat_dir = people_dir / cat_row["category"]
                if cat_dir.is_dir():
                    candidate = cat_dir / cid
                    if candidate.is_dir():
                        return candidate

    # 3. Determine primary group slug to check primary location
    for cid in candidate_ids:
        group_row = connection.execute(
            """
            SELECT g.id, g.slug FROM groups g
            JOIN person_groups pg ON pg.group_id = g.id
            WHERE pg.person_id = ? AND pg.is_primary = 1
            """,
            (cid,),
        ).fetchone()

        if group_row:
            slug = group_row["slug"]
            primary_dir = people_dir / slug
            if primary_dir.is_dir():
                candidate = primary_dir / cid
                if candidate.is_dir():
                    return candidate
            for sub in people_dir.iterdir():
                if sub.is_dir() and sub.name.lower() == slug.lower() and sub.name != "_archived":
                    candidate = sub / cid
                    if candidate.is_dir():
                        return candidate

    # 4. Check other directories under people_dir (ignoring _archived and hidden dirs)
    for sub in people_dir.iterdir():
        if sub.is_dir() and sub.name != "_archived" and not sub.name.startswith("."):
            for cid in candidate_ids:
                candidate = sub / cid
                if candidate.is_dir():
                    return candidate

    return None


def expected_person_folder(
    connection: sqlite3.Connection,
    person_id: str,
    group_id: str | None = None,
    category: str | None = None,
    root: Path | None = None,
) -> Path:
    """Return the expected canonical folder path for a person without touching the filesystem."""
    people_dir = DataRootManager.get_people_dir(root) if root else config.PEOPLE_DIR
    resolved_id = resolve_canonical_id(connection, person_id)

    if is_canonical_connection(connection):
        from .domain.canonical.ids import (
            is_valid_canonical_person_id,
            is_valid_unresolved_person_id,
        )

        if not (
            is_valid_canonical_person_id(resolved_id)
            or is_valid_unresolved_person_id(resolved_id)
        ):
            raise ValueError(f"Invalid canonical person ID for filesystem path: {resolved_id!r}")

    # Unresolved people live directly under People/
    if resolved_id.startswith("unknown_person--"):
        return people_dir / resolved_id

    # If category provided or in database
    target_category = category
    if not target_category:
        has_cat = connection.execute(
            "SELECT 1 FROM pragma_table_info('people') WHERE name = 'category'"
        ).fetchone()
        if has_cat:
            cat_row = connection.execute(
                "SELECT category FROM people WHERE id = ?", (resolved_id,)
            ).fetchone()
            if cat_row and cat_row["category"]:
                target_category = cat_row["category"]

    if target_category in ("Me", "Family", "Friends"):
        target_dir = people_dir / target_category
        if target_dir.exists():
            return target_dir / resolved_id
        for sub in people_dir.iterdir():
            if sub.is_dir() and sub.name.lower() == target_category.lower() and sub.name != "_archived":
                return sub / resolved_id
        return target_dir / resolved_id

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
            (resolved_id,),
        ).fetchone()
    if group_row is None:
        group_row = connection.execute(
            "SELECT id, slug FROM groups WHERE id = 'family'"
        ).fetchone()
    if group_row is None:
        group_row = connection.execute(
            "SELECT id, slug FROM groups WHERE id = 'other'"
        ).fetchone()
    slug = group_row["slug"] if group_row else "Family"

    target_group_dir = people_dir / slug
    if not target_group_dir.exists() and people_dir.exists():
        for sub in people_dir.iterdir():
            if sub.is_dir() and sub.name.lower() == slug.lower() and sub.name != "_archived":
                target_group_dir = sub
                break

    return target_group_dir / resolved_id


def find_journal_path(
    connection: sqlite3.Connection, person_id: str, root: Path | None = None
) -> tuple[Path, bool]:
    """Return (canonical_journal_path, exists) without modifying the filesystem.
    Checks canonical journal(personal thoughts).md first, then legacy journal.md.
    """
    resolved_id = resolve_canonical_id(connection, person_id)
    folder = find_person_folder(connection, resolved_id, root=root)
    if folder is not None:
        canonical_journal = folder / "journal(personal thoughts).md"
        if canonical_journal.is_file():
            return canonical_journal, True
        legacy_journal = folder / "journal.md"
        if legacy_journal.is_file():
            return legacy_journal, True
        people_dir = DataRootManager.get_people_dir(root) if root else config.PEOPLE_DIR
        if (root and (root / "Database" / "People").exists()) or (people_dir.name == "People" and people_dir.parent.name == "Database"):
            return legacy_journal, False
        return canonical_journal, False

    expected = expected_person_folder(connection, resolved_id, root=root)
    people_dir = DataRootManager.get_people_dir(root) if root else config.PEOPLE_DIR
    if (root and (root / "Database" / "People").exists()) or (people_dir.name == "People" and people_dir.parent.name == "Database"):
        return expected / "journal.md", False
    return expected / "journal(personal thoughts).md", False


def ensure_person_folder(
    connection: sqlite3.Connection,
    person_id: str,
    group_id: str | None = None,
    category: str | None = None,
    root: Path | None = None,
) -> Path:
    """Return the canonical person folder, creating it on disk if absent.

    MUTATING operation - for explicit creation, repair, or write paths only.
    """
    if root:
        DataRootManager.ensure_structure(root)
    else:
        config.ensure_root_dirs()
    resolved_id = resolve_canonical_id(connection, person_id)
    existing = find_person_folder(connection, resolved_id, root=root)
    if existing is not None:
        return existing

    folder = expected_person_folder(connection, resolved_id, group_id=group_id, category=category, root=root)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def ensure_journal(
    connection: sqlite3.Connection, person_id: str, root: Path | None = None
) -> Path:
    """Return the canonical journal path, creating the folder and file if absent.

    MUTATING operation - for explicit creation, repair, or write paths only.
    """
    resolved_id = resolve_canonical_id(connection, person_id)
    person = connection.execute(
        "SELECT id, name FROM people WHERE id = ?", (resolved_id,)
    ).fetchone()
    if person is None:
        raise LookupError(f"Unknown person: {person_id}")
    folder = ensure_person_folder(connection, resolved_id, root=root)
    canonical_j = folder / "journal(personal thoughts).md"
    legacy_j = folder / "journal.md"

    if canonical_j.exists():
        return canonical_j
    if legacy_j.exists():
        return legacy_j

    name = person["name"] if person["name"] else resolved_id
    header = f"# {name}\n\n"

    people_dir = DataRootManager.get_people_dir(root) if root else config.PEOPLE_DIR
    if (root and (root / "Database" / "People").exists()) or (people_dir.name == "People" and people_dir.parent.name == "Database"):
        legacy_j.write_text(header, encoding="utf-8", newline="\n")
        return legacy_j

    canonical_j.write_text(header, encoding="utf-8", newline="\n")
    return canonical_j
