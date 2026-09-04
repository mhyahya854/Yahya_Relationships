"""Path and configuration resolution for the People Relationships backend."""

import os
import sys
from pathlib import Path


def _repo_root() -> Path:
    """Repository root: Codebase/App/Backend/config.py -> parents[3]."""
    return Path(__file__).resolve().parents[3]


BACKEND_DIR = Path(__file__).resolve().parent
CODEBASE_DIR = BACKEND_DIR.parents[1]
SCRIPTS_DIR = CODEBASE_DIR / "Scripts"

# Ensure Codebase and Scripts are importable
for path in (CODEBASE_DIR, SCRIPTS_DIR, _repo_root()):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

SCHEMA_PATH = BACKEND_DIR / "schema.sql"

APP_NAME = "People Relationships"
APP_VERSION = "1.0.0"
APP_SCHEMA_VERSION = 1

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = int(os.environ.get("PR_BACKEND_PORT", "8765"))


def __getattr__(name: str):
    from .data_root import DataRootManager

    if name == "ROOT":
        return DataRootManager.resolve_active_root()
    if name == "DB_PATH":
        return DataRootManager.get_database_path()
    if name == "PEOPLE_DIR":
        return DataRootManager.get_people_dir()
    if name == "CONFIG_DIR":
        return DataRootManager.get_config_dir()
    if name == "BACKUP_DIR":
        return DataRootManager.get_backups_dir()
    if name == "EXPORTS_DIR":
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


def ensure_root_dirs() -> None:
    from .data_root import DataRootManager
    DataRootManager.ensure_structure()


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
