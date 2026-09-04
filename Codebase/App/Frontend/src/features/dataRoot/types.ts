export interface ValidationIssue {
  code: string;
  severity: "error" | "warning";
  message: string;
  details?: Record<string, unknown>;
}

export interface DataRootHealth {
  ok: boolean;
  active_root: string;
  database?: {
    integrity: string;
    people_count: number;
    parent_child_facts_count: number;
    marriages_count: number;
  };
  filesystem?: {
    missing_person_folders: string[];
    orphan_person_folders: string[];
    missing_journals: string[];
    archived_active_mismatches: string[];
    duplicate_folder_ids: string[];
  };
  issues: ValidationIssue[];
}

export interface DataRootStatus {
  active_root: string;
  database_path: string;
  people_dir: string;
  backups_dir: string;
  config_dir: string;
  read_only: boolean;
  maintenance_locked: boolean;
  maintenance_operation?: string | null;
  health: DataRootHealth;
}
