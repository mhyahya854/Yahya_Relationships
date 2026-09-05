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
  domain: "family" | "general";
  relationship_type: string;
  label_en: string;
  label_ur: string | null;
  derived: boolean;
  directionality?: string;
  reverse_label_en?: string | null;
  notes?: string | null;
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
  exists?: boolean;
}

export interface SearchResult {
  category: "PERSON" | "RELATIONSHIP" | "GROUP" | "JOURNAL";
  person_id: string | null;
  relationship_id?: number;
  title: string;
  subtitle: string;
  match: string;
}

export interface BackupInfo {
  name: string;
  path: string;
  has_manifest: boolean;
  created?: string;
  label?: string | null;
  files?: number;
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
