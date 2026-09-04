import uvicorn

from . import config


def main() -> None:
    from .data_root.manager import DataRootManager

    active_root = DataRootManager.resolve_active_root()
    if active_root.exists():
        config.ensure_root_dirs()
    uvicorn.run(
        "app.backend.api.main:app",
        host=config.DEFAULT_HOST,
        port=config.DEFAULT_PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()
