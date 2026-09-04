import type {
  ExpansionContribution,
  ExpansionFilter,
  GraphEdgeDto,
  GraphNodeDto,
  RelationshipPath,
} from "../types";

export interface GraphState {
  /** Contribution bookkeeping per "person:filter" expansion. */
  expansions: Record<string, ExpansionContribution>;
  /** Nodes that are always present (perspective, pinned selections). */
  pinned: Set<string>;
  selectedPersonId: string | null;
}

export function allFilters(): ExpansionFilter[] {
  return ["parents", "children", "siblings", "spouses", "general"];
}

export function mergeNeighbors(
  current: {
    nodes: Map<string, GraphNodeDto>;
    edges: Map<string, GraphEdgeDto>;
  },
  payload: { nodes: GraphNodeDto[]; edges: GraphEdgeDto[] },
): { addedNodes: string[]; addedEdges: string[] } {
  const addedNodes: string[] = [];
  const addedEdges: string[] = [];
  for (const node of payload.nodes) {
    if (!current.nodes.has(node.id)) {
      current.nodes.set(node.id, node);
      addedNodes.push(node.id);
    } else {
      // Refresh relation labels when the perspective or payload changed.
      const existing = current.nodes.get(node.id)!;
      current.nodes.set(node.id, {
        ...existing,
        ...node,
      });
    }
  }
  for (const edge of payload.edges) {
    if (!current.edges.has(edge.id)) {
      current.edges.set(edge.id, edge);
      addedEdges.push(edge.id);
    }
  }
  return { addedNodes, addedEdges };
}

export function removeExpansion(
  expansions: Record<string, ExpansionContribution>,
  key: string,
  current: {
    nodes: Map<string, GraphNodeDto>;
    edges: Map<string, GraphEdgeDto>;
    pinned: Set<string>;
  },
): void {
  const contribution = expansions[key];
  if (!contribution) return;
  delete expansions[key];

  const stillUsedNodes = new Set<string>();
  const stillUsedEdges = new Set<string>();
  for (const other of Object.values(expansions)) {
    other.nodes.forEach((id) => stillUsedNodes.add(id));
    other.edges.forEach((id) => stillUsedEdges.add(id));
  }
  for (const edgeId of contribution.edges) {
    if (!stillUsedEdges.has(edgeId)) {
      current.edges.delete(edgeId);
    }
  }
  const survivingEdges = [...current.edges.values()];
  for (const nodeId of contribution.nodes) {
    if (
      !stillUsedNodes.has(nodeId) &&
      !current.pinned.has(nodeId) &&
      current.nodes.has(nodeId) &&
      !survivingEdges.some(
        (edge) => edge.source === nodeId || edge.target === nodeId,
      )
    ) {
      current.nodes.delete(nodeId);
    }
  }
}

export function pathMembers(path: RelationshipPath): {
  nodeIds: string[];
  edgePairs: Array<[string, string]>;
} {
  const nodeIds = path.nodes.map((node) => node.id);
  const edgePairs: Array<[string, string]> = [];
  for (const edge of path.edges) {
    edgePairs.push([edge.from, edge.to]);
  }
  return { nodeIds, edgePairs };
}
