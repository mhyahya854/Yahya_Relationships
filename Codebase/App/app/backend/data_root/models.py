"""Data Root Models and Data Schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ValidationIssue:
    code: str
    severity: str  # "error", "warning", "info"
    message: str
    person_id: Optional[str] = None
    path: Optional[str] = None
    suggested_action: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "person_id": self.person_id,
            "path": self.path,
            "suggested_action": self.suggested_action,
        }


DataRootIssue = ValidationIssue


@dataclass
class DatabaseHealth:
    integrity: str  # "ok" or error string
    people_count: int
    parent_child_count: int
    marriages_count: int
    schema_version: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "integrity": self.integrity,
            "people_count": self.people_count,
            "parent_child_count": self.parent_child_count,
            "marriages_count": self.marriages_count,
            "schema_version": self.schema_version,
        }


@dataclass
class FilesystemHealth:
    missing_person_folders: List[str] = field(default_factory=list)
    orphan_person_folders: List[str] = field(default_factory=list)
    missing_journals: List[str] = field(default_factory=list)
    archived_active_mismatches: List[str] = field(default_factory=list)
    duplicate_folder_identities: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "missing_person_folders": self.missing_person_folders,
            "orphan_person_folders": self.orphan_person_folders,
            "missing_journals": self.missing_journals,
            "archived_active_mismatches": self.archived_active_mismatches,
            "duplicate_folder_identities": self.duplicate_folder_identities,
        }


@dataclass
class DataRootHealth:
    ok: bool
    read_only: bool
    layout_mode: str  # "portable" or "legacy_repo_root"
    root_path: str
    database: Optional[DatabaseHealth] = None
    filesystem: Optional[FilesystemHealth] = None
    issues: List[ValidationIssue] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "read_only": self.read_only,
            "layout_mode": self.layout_mode,
            "root_path": self.root_path,
            "database": self.database.to_dict() if self.database else None,
            "filesystem": self.filesystem.to_dict() if self.filesystem else None,
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass
class BackupInfo:
    id: str
    timestamp: str
    label: str
    app_version: str
    schema_version: int
    data_root_version: int
    file_count: int
    total_size_bytes: int
    person_count: int
    journal_count: int
    verified: bool
    integrity_status: str  # "ok", "corrupted", "unverified"
    path: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "label": self.label,
            "app_version": self.app_version,
            "schema_version": self.schema_version,
            "data_root_version": self.data_root_version,
            "file_count": self.file_count,
            "total_size_bytes": self.total_size_bytes,
            "person_count": self.person_count,
            "journal_count": self.journal_count,
            "verified": self.verified,
            "integrity_status": self.integrity_status,
            "path": self.path,
        }
