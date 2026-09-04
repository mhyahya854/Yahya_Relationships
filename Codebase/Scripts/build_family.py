"""Legacy CLI wrapper — delegates to the canonical kinship engine.

The single canonical implementation lives at
``Codebase/App/app/backend/domain/family/engine.py``. This thin wrapper keeps
the historical entry point (``Scripts/build_family.py``) working for the CLI
and npm scripts without maintaining a second copy of the engine.
"""

import sys
from pathlib import Path

# Script entry-point bootstrap: make the backend package importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "App"))

from app.backend.domain.family.engine import main, validate  # noqa: F401, E402

if __name__ == "__main__":
    main()
