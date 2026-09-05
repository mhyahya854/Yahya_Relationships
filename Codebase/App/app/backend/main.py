import argparse
import os
import sys
import threading
import uvicorn

try:
    from . import config
    from .api.main import app
except (ImportError, ValueError):
    from app.backend import config
    from app.backend.api.main import app


def _start_parent_watchdog(parent_pid: int) -> None:
    def _watchdog() -> None:
        import time

        while True:
            time.sleep(1.0)
            is_alive = False
            if sys.platform == "win32":
                import ctypes

                SYNCHRONIZE = 0x00100000
                process = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, parent_pid)
                if process != 0:
                    WAIT_TIMEOUT = 258
                    res = ctypes.windll.kernel32.WaitForSingleObject(process, 0)
                    ctypes.windll.kernel32.CloseHandle(process)
                    is_alive = res == WAIT_TIMEOUT
            else:
                try:
                    os.kill(parent_pid, 0)
                    is_alive = True
                except OSError:
                    is_alive = False

            if not is_alive:
                os._exit(0)

    thread = threading.Thread(target=_watchdog, daemon=True)
    thread.start()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="People Relationships FastAPI Backend")
    parser.add_argument(
        "--host",
        default=config.DEFAULT_HOST,
        help="Host interface (must be loopback 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=config.DEFAULT_PORT,
        help="Port to listen on (default 8765)",
    )
    parser.add_argument(
        "--parent-pid",
        type=int,
        default=None,
        help="Parent process ID to monitor for auto-termination",
    )
    return parser.parse_args()


def main() -> None:
    try:
        from .data_root.manager import DataRootManager
    except (ImportError, ValueError):
        from app.backend.data_root.manager import DataRootManager

    args = parse_args()
    host = args.host.strip()
    if host not in ("127.0.0.1", "localhost", "::1"):
        sys.stderr.write(f"Refusing non-loopback host {host!r}. Binding strictly to 127.0.0.1\n")
    port = args.port

    parent_pid = args.parent_pid or os.environ.get("PR_PARENT_PID")
    if parent_pid:
        try:
            _start_parent_watchdog(int(parent_pid))
        except (ValueError, TypeError):
            pass

    if DataRootManager.has_configured_root():
        active_root = DataRootManager.resolve_active_root()
        if active_root.exists():
            try:
                config.ensure_root_dirs()
            except Exception:
                pass

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
