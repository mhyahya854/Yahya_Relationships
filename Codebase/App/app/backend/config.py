"""Path and configuration resolution for the People Relationships backend.

This module is the single authority for project-layout paths. Importability
of ``app`` is provided by the editable install (Codebase/App/pyproject.toml),
by ``Codebase/pytest.ini`` under pytest, and by the entry-point bootstraps in
``main.py`` / ``api/main.py`` — no sys.path manipulation happens here.
"""

import os
import sys
from pathlib import Path

IS_FROZEN = getattr(sys, "frozen", False)


def _repo_root() -> Path:
    """Project root: Codebase/App/app/backend/config.py -> parents[4]."""
    if IS_FROZEN:
        # In packaged/frozen mode, there is no source repo root
        return Path(getattr(sys, "_MEIPASS", sys.executable)).resolve()
    return Path(__file__).resolve().parents[4]


if IS_FROZEN:
    _bundle_base = Path(getattr(sys, "_MEIPASS", sys.executable)).resolve()
    _candidate_backend = _bundle_base / "app" / "backend"
    BACKEND_DIR = _candidate_backend if _candidate_backend.exists() else _bundle_base
    PROJECT_ROOT = _bundle_base
    CODEBASE_ROOT = _bundle_base
    APP_DIR = _bundle_base
    SCRIPTS_DIR = _bundle_base
    RESOURCES_DIR = _bundle_base
    VENDOR_DIR = _bundle_base
    DOCUMENTATION_ROOT = _bundle_base
else:
    BACKEND_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = _repo_root()
    CODEBASE_ROOT = BACKEND_DIR.parents[2]
    APP_DIR = BACKEND_DIR.parents[1]
    SCRIPTS_DIR = CODEBASE_ROOT / "Scripts"
    RESOURCES_DIR = CODEBASE_ROOT / "Resources"
    VENDOR_DIR = RESOURCES_DIR / "Vendor"
    DOCUMENTATION_ROOT = PROJECT_ROOT / "Documentation"

# Backwards-compatible alias for the historical name.
CODEBASE_DIR = CODEBASE_ROOT

SCHEMA_PATH = BACKEND_DIR / "schema.sql"
if not SCHEMA_PATH.exists() and IS_FROZEN:
    _alt_schema = Path(getattr(sys, "_MEIPASS", sys.executable)).resolve() / "schema.sql"
    if _alt_schema.exists():
        SCHEMA_PATH = _alt_schema

APP_NAME = "People Relationships"
APP_VERSION = "1.0.0"
APP_SCHEMA_VERSION = 1

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = int(os.environ.get("PR_BACKEND_PORT", "8765"))


def __getattr__(name: str):
    from .data_root import DataRootManager

    if name == "ROOT":
        return DataRootManager.resolve_active_root()
    if name == "DATABASE_ROOT":
        return DataRootManager.resolve_active_root() / "Database"
    if name in ("DB_PATH", "DATABASE_PATH"):
        return DataRootManager.get_database_path()
    if name in ("PEOPLE_DIR", "PEOPLE_ROOT"):
        return DataRootManager.get_people_dir()
    if name == "CONFIG_DIR":
        return DataRootManager.get_config_dir()
    if name in ("BACKUP_DIR", "BACKUPS_ROOT"):
        return DataRootManager.get_backups_dir()
    if name in ("EXPORTS_DIR", "EXPORTS_ROOT"):
        return DataRootManager.get_exports_dir()
    if name == "SOURCES_DIR":
        r = DataRootManager.resolve_active_root()
        db_sources = r / "Database" / "Sources"
        if db_sources.exists():
            return db_sources
        return r / "sources"
    if name == "STATE_PATH":
        return DataRootManager.get_config_dir() / "state.json"
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def ensure_root_dirs(*, create: bool = False) -> None:
    from .data_root import DataRootManager
    DataRootManager.ensure_structure(create=create)


def load_state() -> dict:
    import json
    from .data_root import DataRootManager

    ensure_root_dirs()
    state_path = DataRootManager.get_config_dir() / "state.json"
    if state_path.exists():
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (ValueError, OSError):
            pass
    return {}


def save_state(state: dict) -> None:
    import json
    import tempfile
    from .data_root import DataRootManager

    ensure_root_dirs()
    config_dir = DataRootManager.get_config_dir()
    state_path = config_dir / "state.json"
    payload = json.dumps(state, ensure_ascii=False, indent=2)
    fd, tmp_name = tempfile.mkstemp(
        prefix=".state-", suffix=".tmp", dir=str(config_dir)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, state_path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
