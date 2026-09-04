import type { Edge, Node } from "@xyflow/react";

export type ExpansionFilter =
  | "parents"
  | "children"
  | "siblings"
  | "spouses"
  | "general";

export interface PersonBrief {
  id: string;
  name: string;
  gender?: string | null;
  birth_year?: number | null;
}

export interface GraphNodeDto {
  id: string;
  name: string;
  gender?: string | null;
  birth_year?: number | null;
  is_perspective?: boolean;
  is_virtual?: boolean;
  relation_label_en?: string | null;
  relation_label_ur?: string | null;
}

export interface GraphEdgeDto {
  id: string;
  source: string;
  target: string;
  domain: "family" | "general";
  type: string;
  subtype: string;
}

export interface GraphNeighborsResponse {
  ok: boolean;
  center: PersonBrief;
  perspective: PersonBrief;
  filters: string[];
  nodes: GraphNodeDto[];
  edges: GraphEdgeDto[];
}

export interface PathNode {
  id: string;
  name: string;
  is_virtual?: boolean;
}

export interface PathEdge {
  from: string;
  to: string;
  type: string;
  subtype: string;
  role?: string;
}

export interface RelationshipPath {
  id: string;
  domain: "family" | "general";
  relationship_type: string;
  label_en: string;
  label_ur: string | null;
  side: string;
  degree: number | null;
  removal: number | null;
  distance: number;
  common_ancestors: Array<{ id: string; name: string; is_virtual?: boolean }>;
  nodes: PathNode[];
  edges: PathEdge[];
  derived: boolean;
}

export interface PathsResponse {
  ok: boolean;
  perspective: PersonBrief;
  target: PersonBrief;
  paths: RelationshipPath[];
  truncated: boolean;
}

export interface RelationshipEntry {
  domain: "family" | "general";
  relationship_type: string;
  label_en: string;
  label_ur: string | null;
  derived: boolean;
  directionality?: string;
  reverse_label_en?: string | null;
}

export interface RelationshipResultDto {
  ok: boolean;
  perspective: { id: string; name: string };
  target: { id: string; name: string };
  primary: RelationshipEntry[];
  additional: RelationshipEntry[];
}

export interface PersonNodeData {
  id: string;
  name: string;
  subtitle?: string;
  subtitleUr?: string;
  isPerspective?: boolean;
  isVirtual?: boolean;
}

export type FlowNode = Node;
export type FlowEdge = Edge<{ relationLabel?: string }>;

export interface ExpansionContribution {
  nodes: string[];
  edges: string[];
}

export type ExpansionKey = string; // `${personId}:${filter}`
