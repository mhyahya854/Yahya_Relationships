"""Central Data Root Manager.

Authoritative manager for resolving, initializing, binding, moving, and switching
the user's single canonical Data Root directory.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .errors import (
    DataRootDestinationConflictError,
    DataRootBootstrapInvalidError,
    DataRootInvalidError,
    DataRootNotFoundError,
    DataRootReadOnlyError,
)


def _repo_root() -> Path:
    """Project root: Codebase/App/app/backend/data_root/manager.py -> parents[5]."""
    return Path(__file__).resolve().parents[5]


def _user_bootstrap_config_path() -> Path:
    """OS-specific bootstrap pointer file pointing to active Data Root.

    ``PEOPLE_RELATIONSHIPS_BOOTSTRAP`` overrides the location entirely (used
    by the test suite so the real user-level config is never touched).
    """
    override = os.environ.get("PEOPLE_RELATIONSHIPS_BOOTSTRAP")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / "people-relationships" / "bootstrap.json"


class DataRootManager:
    """Singleton/Central manager for active data root path resolution."""

    _override_root: Optional[Path] = None
    CANONICAL_LAYOUT = "canonical-v3"
    INCOMPLETE_MARKERS = (".migration_incomplete.json", ".restore_incomplete.json")

    @classmethod
    def set_override_root(cls, path: Path | None) -> None:
        """Override active root (useful for isolated tests)."""
        cls._override_root = path.resolve() if path else None

    @classmethod
    def bootstrap_status(cls) -> Dict[str, Any]:
        """Read the active-root authority without creating or repairing anything."""
        if cls._override_root is not None:
            return {"configured": True, "invalid": False, "active_root": cls._override_root, "source": "override"}

        env_root = os.environ.get("PEOPLE_RELATIONSHIPS_ROOT")
        if env_root:
            return {
                "configured": True,
                "invalid": False,
                "active_root": Path(env_root).expanduser().resolve(),
                "source": "environment",
            }

        bootstrap_file = _user_bootstrap_config_path()
        explicit_bootstrap = "PEOPLE_RELATIONSHIPS_BOOTSTRAP" in os.environ
        if bootstrap_file.exists():
            try:
                payload = json.loads(bootstrap_file.read_text(encoding="utf-8"))
                active_root = payload.get("active_root") if isinstance(payload, dict) else None
                if not isinstance(active_root, str) or not active_root.strip():
                    raise ValueError("active_root must be a non-empty string")
                return {
                    "configured": True,
                    "invalid": False,
                    "active_root": Path(active_root).expanduser().resolve(),
                    "source": "bootstrap",
                    "payload": payload,
                }
            except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
                return {
                    "configured": True,
                    "invalid": True,
                    "active_root": None,
                    "source": "bootstrap",
                    "error": str(exc),
                }

        if explicit_bootstrap:
            return {"configured": False, "invalid": False, "active_root": None, "source": "bootstrap"}

        if not getattr(sys, "frozen", False):
            repo = _repo_root()
            if (repo / "Database" / "relationships.db").exists() or (repo / "Database" / "Main" / "family.db").exists():
                return {"configured": True, "invalid": False, "active_root": repo, "source": "source_fallback"}

        return {"configured": False, "invalid": False, "active_root": None, "source": "bootstrap"}

    @classmethod
    def has_configured_root(cls) -> bool:
        """Check whether an explicit active data root has been configured."""
        return bool(cls.bootstrap_status()["configured"])

    @classmethod
    def get_bootstrap_root(cls) -> Path:
        """Resolve current active root path from override, env, bootstrap file, or repo root."""
        status = cls.bootstrap_status()
        if status["invalid"]:
            raise DataRootBootstrapInvalidError(detail={"path": str(_user_bootstrap_config_path())})
        if status["active_root"] is not None:
            return status["active_root"]
        bootstrap_file = _user_bootstrap_config_path()
        return bootstrap_file.parent / "unconfigured_data_root"

    @classmethod
    def set_active_root_pointer(cls, new_root: Path) -> None:
        """Atomically update the bootstrap pointer; the old bytes survive any failure."""
        resolved = new_root.resolve()
        bootstrap_file = _user_bootstrap_config_path()
        payload = {
            "active_root": str(resolved),
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        metadata = cls.read_root_metadata(resolved)
        if metadata.get("root_id"):
            payload["root_id"] = metadata["root_id"]
        bootstrap_file.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=".bootstrap-", suffix=".tmp", dir=str(bootstrap_file.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, bootstrap_file)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise
        if cls._override_root is not None:
            cls._override_root = resolved

    @classmethod
    def read_root_metadata(cls, root: Path) -> Dict[str, Any]:
        metadata_path = cls.get_config_dir(root) / "data-root.json"
        if not metadata_path.is_file():
            return {}
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}

    @classmethod
    def resolve_active_root(cls) -> Path:
        return cls.get_bootstrap_root()

    @classmethod
    def has_incomplete_operation(cls, root: Path | None = None) -> bool:
        r = root.resolve() if root else cls.resolve_active_root()
        return any((r / name).is_file() for name in cls.INCOMPLETE_MARKERS)

    @classmethod
    def is_canonical_root(cls, root: Path | None = None) -> bool:
        """Return whether a root is committed to the Phase-11 canonical layout.

        This deliberately does not require ``relationships.db`` to exist: a
        missing canonical database must remain a visible failure, never turn
        into permission to fall back to historical ``family.db``.
        """
        r = root.resolve() if root else cls.resolve_active_root()
        metadata = cls.read_root_metadata(r)
        migration_marker = (r / ".migration_incomplete.json").is_file()
        restore_marker = r / ".restore_incomplete.json"
        restore_targets_canonical = False
        if restore_marker.is_file():
            try:
                marker_payload = json.loads(restore_marker.read_text(encoding="utf-8"))
                restore_targets_canonical = marker_payload.get("target_layout") == "canonical"
            except (OSError, UnicodeError, json.JSONDecodeError):
                restore_targets_canonical = True
        return bool(
            metadata.get("storage_layout") == cls.CANONICAL_LAYOUT
            or (r / "Database" / "relationships.db").is_file()
            or (r / "relationships.db").is_file()
            or (r / "data" / "relationships.db").is_file()
            or (r / "Database" / "HISTORICAL_FAMILY_DB.md").is_file()
            or migration_marker
            or restore_targets_canonical
        )

    @classmethod
    def get_database_path(cls, root: Path | None = None) -> Path:
        r = root.resolve() if root else cls.resolve_active_root()
        # 1. Primary canonical SQLite store: Database/relationships.db
        db_rel = r / "Database" / "relationships.db"
        if db_rel.exists():
            return db_rel
        # 2. Directly under root relationships.db
        db_rel_root = r / "relationships.db"
        if db_rel_root.exists():
            return db_rel_root
        # 3. Portable backup snapshot layout: data/relationships.db
        db_data_rel = r / "data" / "relationships.db"
        if db_data_rel.exists():
            return db_data_rel
        # A root committed to canonical storage stays canonical even if its DB
        # is missing. Returning the expected path makes all callers fail closed.
        if cls.is_canonical_root(r):
            return db_rel
        # 4. Fallback to legacy family.db locations only for unmigrated roots.
        db_main = r / "Database" / "Main" / "family.db"
        if db_main.exists():
            return db_main
        db_data = r / "data" / "family.db"
        if db_data.exists():
            return db_data
        db_root = r / "family.db"
        if db_root.exists():
            return db_root

        # Otherwise default to legacy main_db for unmigrated / newly initialized roots
        return db_main

    @classmethod
    def get_people_dir(cls, root: Path | None = None) -> Path:
        r = root.resolve() if root else cls.resolve_active_root()
        # 1. Canonical roots always use top-level People/, including repair states.
        if cls.is_canonical_root(r):
            return r / "People"

        # 2. Legacy Pass 4 / Phase 8 layout: Database/People
        db_people = r / "Database" / "People"
        if db_people.exists():
            return db_people

        # 3. Portable backup layout: people/
        legacy_people = r / "people"
        if legacy_people.exists():
            return legacy_people

        # 4. Canonical top-level People/ directory (if exists)
        people_top = r / "People"
        if people_top.exists():
            return people_top

        # Default: if Database/Main exists, default to Database/People
        if (r / "Database" / "Main").exists():
            return db_people
        return people_top

    @classmethod
    def get_backups_dir(cls, root: Path | None = None) -> Path:
        r = root.resolve() if root else cls.resolve_active_root()
        legacy_backups = r / "backups"
        if legacy_backups.exists():
            return legacy_backups
        return r / "Backups"

    @classmethod
    def get_config_dir(cls, root: Path | None = None) -> Path:
        r = root.resolve() if root else cls.resolve_active_root()
        config_db = r / "Database" / "Config"
        if config_db.exists():
            return config_db
        legacy_config = r / "config"
        if legacy_config.exists():
            return legacy_config
        return config_db

    @classmethod
    def get_exports_dir(cls, root: Path | None = None) -> Path:
        r = root.resolve() if root else cls.resolve_active_root()
        exports_db = r / "Database" / "Exports"
        if exports_db.exists():
            return exports_db
        legacy_exports = r / "exports"
        if legacy_exports.exists():
            return legacy_exports
        return exports_db

    @classmethod
    def is_read_only(cls, root: Path | None = None) -> bool:
        r = root.resolve() if root else cls.resolve_active_root()
        if not r.exists():
            return False
        # Status inspection must be read-only. Avoid the former create/delete
        # probe, which mutated a root merely by asking for its health.
        return not os.access(r, os.W_OK | os.X_OK)

    @classmethod
    def is_active_root_available(cls) -> bool:
        r = cls.resolve_active_root()
        return r.exists() and cls.get_database_path(r).exists()

    @classmethod
    def ensure_structure(
        cls,
        root: Path | None = None,
        *,
        create: bool = False,
        canonical: bool | None = None,
    ) -> None:
        """Ensure Data Root directory layout exists."""
        r = root.resolve() if root else cls.resolve_active_root()
        if not r.exists():
            if not create:
                raise DataRootNotFoundError(
                    f"Data Root directory does not exist at '{r}'. Refusing to create directories silently.",
                    detail={"code": "DATA_ROOT_NOT_FOUND", "path": str(r)},
                )
            r.mkdir(parents=True, exist_ok=True)
        canonical_layout = cls.is_canonical_root(r) if canonical is None else canonical
        if canonical_layout:
            (r / "People" / "Me").mkdir(parents=True, exist_ok=True)
            (r / "People" / "Family").mkdir(parents=True, exist_ok=True)
            (r / "People" / "Friends").mkdir(parents=True, exist_ok=True)
        else:
            (r / "Database" / "Main").mkdir(parents=True, exist_ok=True)
            (r / "Database" / "People").mkdir(parents=True, exist_ok=True)
        (r / "Database" / "Config").mkdir(parents=True, exist_ok=True)
        (r / "Database" / "Sources").mkdir(parents=True, exist_ok=True)
        (r / "Database" / "Exports" / "Family").mkdir(parents=True, exist_ok=True)
        (r / "Backups").mkdir(parents=True, exist_ok=True)
        # Raw is deliberately empty at creation time. Its payload is never
        # inferred, unpacked, or otherwise populated by the application.
        (r / "Raw").mkdir(parents=True, exist_ok=True)

        (r / "Database" / "Logs").mkdir(parents=True, exist_ok=True)
        (r / "Backups" / "Manual").mkdir(parents=True, exist_ok=True)
        (r / "Backups" / "Automatic").mkdir(parents=True, exist_ok=True)
        (r / "Backups" / "Safety" / "Pre-Upgrade").mkdir(parents=True, exist_ok=True)
        (r / "Backups" / "Safety" / "Pre-Organization").mkdir(parents=True, exist_ok=True)
        (r / "Backups" / "Safety" / "Pre-Restore").mkdir(parents=True, exist_ok=True)

        meta_file = cls.get_config_dir(r) / "data-root.json"
        meta_file.parent.mkdir(parents=True, exist_ok=True)
        if not meta_file.exists():
            metadata = {
                "format": "people-relationships-data-root",
                "version": 1,
                "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "root_id": uuid.uuid4().hex,
            }
            if canonical_layout:
                metadata["storage_layout"] = cls.CANONICAL_LAYOUT
                metadata["canonical_database"] = "Database/relationships.db"
            meta_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    @classmethod
    def is_backup_snapshot(cls, path: Path) -> bool:
        """Reject selecting a backup directory as live active data root."""
        p = path.resolve()
        parts_lower = [part.lower() for part in p.parts]
        if "backups" in parts_lower or (p / "manifest.json").exists():
            return True
        return False

    @classmethod
    def validate_data_root_structure(cls, path: Path) -> Dict[str, Any]:
        """Validate if a target directory is a valid usable Data Root."""
        p = path.resolve()
        if not p.exists():
            raise DataRootNotFoundError(f"Path '{p}' does not exist.")
        if not p.is_dir() or p.is_symlink():
            raise DataRootInvalidError(
                f"Path '{p}' is not a safe Data Root directory.",
                detail={"code": "UNSAFE_ROOT_PATH"},
            )

        if cls.is_backup_snapshot(p):
            raise DataRootInvalidError(
                f"Path '{p}' is a backup snapshot, not an active Data Root.",
                detail={"code": "BACKUP_SNAPSHOT_REJECTED"},
            )

        db_file = cls.get_database_path(p)
        if not db_file.exists():
            raise DataRootInvalidError(
                f"No SQLite database found at '{db_file}'.",
                detail={"code": "MISSING_DATABASE"},
            )

        people_dir = cls.get_people_dir(p)
        if not people_dir.exists():
            raise DataRootInvalidError(
                f"No 'people' directory found at '{people_dir}'.",
                detail={"code": "MISSING_PEOPLE_DIR"},
            )

        return {
            "valid": True,
            "root_path": str(p),
            "db_path": str(db_file),
            "people_dir": str(people_dir),
        }
