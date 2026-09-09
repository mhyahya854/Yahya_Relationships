export type DataRootState =
  | "UNCONFIGURED"
  | "HEALTHY"
  | "READ_ONLY"
  | "MISSING"
  | "INVALID"
  | "REPAIRABLE"
  | "MAINTENANCE";

export interface ValidationIssue {
  code: string;
  severity: "error" | "warning" | "info";
  message: string;
  path?: string | null;
  suggested_action?: string | null;
}

export interface DataRootHealth {
  ok: boolean;
  read_only: boolean;
  layout_mode: string;
  root_path: string;
  database?: {
    integrity: string;
    people_count: number;
    parent_child_count: number;
    marriages_count: number;
    schema_version: number;
  } | null;
  filesystem?: {
    missing_person_folders: string[];
    orphan_person_folders: string[];
    missing_journals: string[];
    archived_active_mismatches: string[];
    duplicate_folder_identities: string[];
  } | null;
  issues: ValidationIssue[];
}

export interface DataRootStatus {
  configured: boolean;
  first_run: boolean;
  state: DataRootState;
  active_root: string | null;
  last_configured_root: string | null;
  database_path: string | null;
  people_dir: string | null;
  backups_dir: string | null;
  config_dir: string | null;
  read_only: boolean;
  maintenance_locked: boolean;
  maintenance_operation?: string | null;
  root_id?: string | null;
  data_root_format_version?: number | null;
  schema_version?: number | null;
  health: DataRootHealth;
}

export interface DataRootCandidate {
  path: string;
  exists: boolean;
  is_directory: boolean;
  is_empty: boolean;
  is_backup_snapshot: boolean;
  valid_structure: boolean;
  state: DataRootState;
  read_only: boolean;
  health: DataRootHealth | null;
  schema_version: number | null;
  data_root_format_version: number | null;
  root_id: string | null;
  person_count: number;
  journal_count: number;
  issues: ValidationIssue[];
  can_switch: boolean;
}

export interface BackupInspection {
  ok: boolean;
  path: string;
  status: string;
  manifest?: {
    label?: string;
    person_count?: number;
    journal_count?: number;
    sqlite_schema_version?: number;
  };
  issues: ValidationIssue[];
}
