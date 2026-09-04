"""Data Root Custom Exception Classes."""

from typing import Any, Dict, List, Optional


class DataRootError(Exception):
    """Base exception for all Data Root operations."""

    def __init__(self, message: str, code: str = "DATA_ROOT_ERROR", detail: Optional[Any] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.detail = detail

    def to_dict(self) -> Dict[str, Any]:
        res: Dict[str, Any] = {"message": self.message, "code": self.code}
        if self.detail is not None:
            res["detail"] = self.detail
        return res


class DataRootNotFoundError(DataRootError):
    def __init__(self, message: str = "The specified active data root could not be found.", detail: Optional[Any] = None):
        super().__init__(message, code="DATA_ROOT_NOT_FOUND", detail=detail)


class DataRootInvalidError(DataRootError):
    def __init__(self, message: str = "The data root structure or database is invalid.", detail: Optional[Any] = None):
        super().__init__(message, code="DATA_ROOT_INVALID", detail=detail)


class DataRootReadOnlyError(DataRootError):
    def __init__(self, message: str = "Data root directory is read-only. Editing is disabled.", detail: Optional[Any] = None):
        super().__init__(message, code="DATA_ROOT_READ_ONLY", detail=detail)


class DataRootDestinationConflictError(DataRootError):
    def __init__(self, message: str = "Target destination is invalid or contains conflicting data.", detail: Optional[Any] = None):
        super().__init__(message, code="DATA_ROOT_DESTINATION_CONFLICT", detail=detail)


class BackupError(DataRootError):
    def __init__(self, message: str, code: str = "BACKUP_ERROR", detail: Optional[Any] = None):
        super().__init__(message, code=code, detail=detail)


class BackupManifestInvalidError(BackupError):
    def __init__(self, message: str = "Backup manifest is missing or invalid.", detail: Optional[Any] = None):
        super().__init__(message, code="BACKUP_MANIFEST_INVALID", detail=detail)


class BackupHashMismatchError(BackupError):
    def __init__(self, message: str = "Backup file hash does not match manifest.", detail: Optional[Any] = None):
        super().__init__(message, code="BACKUP_HASH_MISMATCH", detail=detail)


class BackupDatabaseInvalidError(BackupError):
    def __init__(self, message: str = "Backup SQLite database failed integrity check.", detail: Optional[Any] = None):
        super().__init__(message, code="BACKUP_DATABASE_INVALID", detail=detail)


class RestoreError(DataRootError):
    def __init__(self, message: str, code: str = "RESTORE_FAILED", detail: Optional[Any] = None):
        super().__init__(message, code=code, detail=detail)


class UndoFilesystemConflictError(DataRootError):
    def __init__(self, message: str = "Person journal was modified externally after the mutation.", detail: Optional[Any] = None):
        super().__init__(message, code="UNDO_FILESYSTEM_CONFLICT", detail=detail)


class MaintenanceOperationInProgressError(DataRootError):
    def __init__(self, message: str = "A data maintenance operation is currently in progress.", detail: Optional[Any] = None):
        super().__init__(message, code="MAINTENANCE_OPERATION_IN_PROGRESS", detail=detail)
