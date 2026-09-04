"""Backend entry point: python -m app.backend.main"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import uvicorn  # noqa: E402

from . import config  # noqa: E402


def main() -> None:
    config.ensure_root_dirs()
    uvicorn.run(
        "app.backend.api.main:app",
        host=config.DEFAULT_HOST,
        port=config.DEFAULT_PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()
