export interface PersonGroup {
  id: string;
  name: string;
  slug: string;
  kind: string;
  is_primary: boolean;
}

export interface Person {
  id: string;
  name: string;
  aliases: string[];
  birth_year: number | null;
  gender: "male" | "female" | "unknown" | null;
  marital_status: "single" | null;
  branch: string | null;
  note_en: string | null;
  note_ur: string | null;
  photo_path: string | null;
  groups: PersonGroup[];
  folder: string | null;
  folder_exists?: boolean;
  journal_exists?: boolean;
}

export interface Group {
  id: string;
  name: string;
  slug: string;
  kind: string;
  display_order: number;
  member_count: number;
}

export interface RelationshipEntry {
  id?: string;
  domain: "family" | "general";
  relationship_type: string;
  semantic_id?: string;
  path_ids?: string[];
  label_en: string;
  label_ur: string | null;
  derived: boolean;
  kind?: string | null;
  side?: string;
  degree?: number | null;
  removal?: number | null;
  common_ancestors?: Array<{ id: string; name: string; is_virtual?: boolean }>;
  explanation?: string;
  directionality?: string;
  reverse_label_en?: string | null;
  notes?: string | null;
  general_relationship_id?: number;
  stored_fact_id?: string;
  stored_fact_kind?: string | null;
  status?: string | null;
}

export interface RelationshipResult {
  perspective: { id: string; name: string };
  target: { id: string; name: string };
  primary: RelationshipEntry[];
  additional: RelationshipEntry[];
}

export interface CompareResult {
  a: { id: string; name: string };
  b: { id: string; name: string };
  a_to_b: RelationshipResult;
  b_to_a: RelationshipResult;
}

export interface Journal {
  person_id: string;
  path: string;
  content: string;
  modified_ns: string | null;
  sha256: string | null;
  exists: boolean;
  saved?: boolean;
}

export interface SearchResult {
  result_id: string;
  category: "PERSON" | "RELATIONSHIP" | "GROUP" | "JOURNAL";
  person_id: string | null;
  relationship_id?: number;
  relationship_kind?: "family" | "general";
  target_person_id?: string;
  perspective_id?: string;
  path_id?: string;
  semantic_id?: string | null;
  derived?: boolean;
  group_id?: string;
  member_ids?: string[];
  member_count?: number;
  matched_alias?: string | null;
  match_kind?: string;
  matched_field?: string;
  matched_fields?: string[];
  person_a_id?: string;
  person_a_name?: string;
  person_b_id?: string;
  person_b_name?: string;
  directionality?: "symmetric" | "directional";
  direction_from?: string | null;
  label_a_to_b?: string;
  label_b_to_a?: string;
  label_en?: string;
  label_ur?: string | null;
  notes?: string | null;
  title: string;
  subtitle: string;
  match: string;
}

export interface SearchResponse {
  ok: boolean;
  query: string;
  normalized_query: string;
  perspective: { id: string; name: string };
  results: SearchResult[];
}

export interface BackupInfo {
  id: string;
  name: string;
  path: string;
  has_manifest: boolean;
  category: "manual" | "automatic" | "safety" | "legacy";
  safety_reason?: string | null;
  timestamp?: string;
  created?: string;
  label?: string | null;
  files?: number;
  file_count?: number;
  total_size_bytes?: number;
  person_count?: number;
  journal_count?: number;
  app_version?: string | null;
  backup_format_version?: number | null;
  schema_version?: number | null;
  verified: boolean;
  integrity_status: string;
  compatibility: {
    ok: boolean;
    status: string;
    backup_schema?: number | null;
    current_schema?: number;
  };
}

export interface BackupIssue {
  code: string;
  message: string;
  path?: string;
}

export interface BackupVerification {
  ok: boolean;
  status: string;
  issues: BackupIssue[];
  db_integrity: string;
  files_checked?: number;
  compatibility: BackupInfo["compatibility"];
}

export interface HermesToolDef {
  name: string;
  description: string;
  parameters: {
    type: string;
    properties: Record<string, unknown>;
    required?: string[];
  };
}

export interface AppState {
  perspective_person_id: string;
  default_perspective_person_id: string;
}

export interface DuplicateCandidate {
  id: string;
  name: string;
  aliases: string[];
  groups?: PersonGroup[];
  reason: string;
}

export interface PersonProfileData {
  person: Person;
  family: {
    parents: Array<{ id: string; name: string; gender: string | null; birth_year: number | null; role: string; kind: string }>;
    spouses: Array<{ id: string; name: string; gender: string | null; birth_year: number | null; status: string; year: number | null; children_status: string | null }>;
    children: Array<{ id: string; name: string; gender: string | null; birth_year: number | null; role: string; kind: string }>;
    siblings: Array<{ id: string; name: string; gender: string | null; birth_year: number | null; type: string | null }>;
  };
  general: Array<{
    id: number;
    other_person: { id: string; name: string };
    type: string;
    label: string;
    directionality: string;
    notes: string | null;
  }>;
  perspective: RelationshipResult | null;
  journal: Journal;
}

export interface DerivedDiffItem {
  person_a_id: string;
  person_a_name: string;
  person_b_id: string;
  person_b_name: string;
  label_en: string;
  label_ur?: string | null;
  side?: string | null;
  path_id?: string | null;
  nodes?: Array<{ id: string; name: string }>;
  degree?: number | null;
  removal?: number | null;
  distance?: number | null;
}

export interface MutationPreviewResult {
  valid: boolean;
  code?: string | null;
  message?: string | null;
  direct_changes: string[];
  derived_added: DerivedDiffItem[];
  derived_removed: DerivedDiffItem[];
  warnings: string[];
}

export interface ParentChildFact {
  id?: number;
  parent_id: string;
  child_id: string;
  role: string;
  kind: string;
}

export interface MarriageFact {
  id?: number;
  spouse_a: string;
  spouse_b: string;
  status: string;
  year?: number | null;
  children_status?: string | null;
}

export interface SiblingGroupFact {
  id: string;
  type?: string | null;
  ordered: boolean;
  members: string[];
}

export interface GeneralRelationshipFact {
  id: number;
  person_a: string;
  person_b: string;
  type: string;
  directionality: "symmetric" | "directional";
  direction_from?: string | null;
  label_a_to_b: string;
  label_b_to_a: string;
  notes?: string | null;
  created_at?: string;
  updated_at?: string;
}
