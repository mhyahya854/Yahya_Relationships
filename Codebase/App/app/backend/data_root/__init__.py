"""Data Root domain package."""

from .errors import (
    BackupDatabaseInvalidError,
    BackupError,
    BackupHashMismatchError,
    BackupManifestInvalidError,
    DataRootDestinationConflictError,
    DataRootError,
    DataRootInvalidError,
    DataRootNotFoundError,
    DataRootReadOnlyError,
    MaintenanceOperationInProgressError,
    RestoreError,
    UndoFilesystemConflictError,
)
from .manager import DataRootManager
from .models import (
    BackupInfo,
    DatabaseHealth,
    DataRootHealth,
    FilesystemHealth,
    ValidationIssue,
)
from .validation import audit_data_root, safe_repair_data_root

__all__ = [
    "DataRootManager",
    "audit_data_root",
    "safe_repair_data_root",
    "DataRootHealth",
    "DatabaseHealth",
    "FilesystemHealth",
    "ValidationIssue",
    "BackupInfo",
    "DataRootError",
    "DataRootNotFoundError",
    "DataRootInvalidError",
    "DataRootReadOnlyError",
    "DataRootDestinationConflictError",
    "BackupError",
    "BackupManifestInvalidError",
    "BackupHashMismatchError",
    "BackupDatabaseInvalidError",
    "RestoreError",
    "UndoFilesystemConflictError",
    "MaintenanceOperationInProgressError",
]
