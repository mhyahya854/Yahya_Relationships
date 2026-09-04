"""Process-local exclusive maintenance lock.

Blocks concurrent user mutations while high-risk background operations
(Restore, Data Root Move, Data Root Switch) are running.
"""

from __future__ import annotations

import threading
from typing import Optional, Tuple

from ..data_root.errors import MaintenanceOperationInProgressError

_MAINTENANCE_LOCK = threading.Lock()
_CURRENT_OPERATION: Optional[str] = None


def acquire_maintenance_lock(operation_name: str) -> bool:
    global _CURRENT_OPERATION
    acquired = _MAINTENANCE_LOCK.acquire(blocking=False)
    if acquired:
        _CURRENT_OPERATION = operation_name
        return True
    return False


def release_maintenance_lock() -> None:
    global _CURRENT_OPERATION
    _CURRENT_OPERATION = None
    try:
        _MAINTENANCE_LOCK.release()
    except RuntimeError:
        pass


def is_maintenance_locked() -> Tuple[bool, Optional[str]]:
    if _MAINTENANCE_LOCK.locked():
        return True, _CURRENT_OPERATION
    return False, None


def check_maintenance_lock() -> None:
    locked, op_name = is_maintenance_locked()
    if locked:
        raise MaintenanceOperationInProgressError(
            f"Operation '{op_name or 'Maintenance'}' is currently in progress. Editing is temporarily blocked."
        )


class MaintenanceLockContext:
    def __init__(self, operation_name: str):
        self.operation_name = operation_name

    def __enter__(self):
        if not acquire_maintenance_lock(self.operation_name):
            _, current_op = is_maintenance_locked()
            raise MaintenanceOperationInProgressError(
                f"Operation '{current_op or 'Maintenance'}' is currently in progress."
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        release_maintenance_lock()
