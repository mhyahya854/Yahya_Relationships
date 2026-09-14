import dagre from "@dagrejs/dagre";
import type { Edge, Node } from "@xyflow/react";

export const NODE_WIDTH = 224;
export const NODE_HEIGHT = 82;

export type ConnectionRegion =
  | "origin"
  | "maternal"
  | "paternal"
  | "external"
  | "family"
  | "path";

type PositionedNode = Node & {
  data: { region?: ConnectionRegion };
};

function slotFor(region: ConnectionRegion, index: number): { x: number; y: number } {
  const column = index % 3;
  const row = Math.floor(index / 3);
  const centeredColumn = column - 1;
  switch (region) {
    case "maternal":
      return { x: -610 + centeredColumn * 236, y: -250 + row * 156 };
    case "paternal":
      return { x: 386 + centeredColumn * 236, y: -250 + row * 156 };
    case "external":
      return { x: -250 + column * 260, y: 280 + row * 152 };
    case "family":
      return { x: -250 + column * 250, y: 130 + row * 148 };
    case "path":
      return { x: -120 + column * 248, y: -70 + row * 148 };
    case "origin":
    default:
      return { x: 0, y: 0 };
  }
}

function overlaps(
  candidate: { x: number; y: number },
  occupied: Array<{ x: number; y: number }>,
): boolean {
  return occupied.some(
    (point) =>
      Math.abs(point.x - candidate.x) < NODE_WIDTH * 0.9 &&
      Math.abs(point.y - candidate.y) < NODE_HEIGHT * 1.25,
  );
}

/**
 * Deterministic connection-oriented layout. It intentionally keeps the origin
 * central and gives maternal, paternal, external, and neutral family context
 * distinct regions instead of letting a generational rank layout read as a
 * second family tree. Existing positions are retained so adding a target does
 * not disturb the visible context.
 */
export function layoutConnectionGraph(
  nodes: Node[],
  centerId?: string,
  previousPositions?: ReadonlyMap<string, { x: number; y: number }>,
): Node[] {
  const occupied: Array<{ x: number; y: number }> = [];
  const regionCounts = new Map<ConnectionRegion, number>();
  const sorted = [...nodes].sort((a, b) => a.id.localeCompare(b.id));

  return sorted.map((node) => {
    const typed = node as PositionedNode;
    const region: ConnectionRegion = node.id === centerId
      ? "origin"
      : typed.data.region ?? "family";
    const existing = previousPositions?.get(node.id);
    if (existing) {
      occupied.push(existing);
      return { ...node, position: existing };
    }

    let index = regionCounts.get(region) ?? 0;
    let position = slotFor(region, index);
    while (overlaps(position, occupied)) {
      index += 1;
      position = slotFor(region, index);
    }
    regionCounts.set(region, index + 1);
    occupied.push(position);
    return { ...node, position };
  });
}

/**
 * Deterministic hierarchical layout. Input nodes/edges are sorted before
 * layout so small graph changes produce stable positions.
 */
export function layoutGraph(
  nodes: Node[],
  edges: Edge[],
  direction: "TB" | "LR" = "TB",
  centerId?: string,
): Node[] {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({
    rankdir: direction,
    nodesep: 44,
    edgesep: 24,
    ranksep: 104,
    marginx: 32,
    marginy: 32,
    acyclicer: "greedy",
    ranker: "tight-tree",
  });

  const sortedNodes = [...nodes].sort((a, b) => a.id.localeCompare(b.id));
  const sortedEdges = [...edges].sort((a, b) =>
    `${a.source}:${a.target}`.localeCompare(`${b.source}:${b.target}`),
  );
  for (const node of sortedNodes) {
    graph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const edge of sortedEdges) {
    graph.setEdge(edge.source, edge.target);
  }
  dagre.layout(graph);

  const positioned = sortedNodes.map((node) => {
    const position = graph.node(node.id);
    return {
      ...node,
      position: { x: position.x - NODE_WIDTH / 2, y: position.y - NODE_HEIGHT / 2 },
    };
  });

  // Keep the chosen central person at a stable coordinate. React Flow can fit
  // the translated graph without making the account owner a layout fixture.
  const center = positioned.find((node) => node.id === centerId);
  if (!center) return positioned;
  const offsetX = center.position.x;
  const offsetY = center.position.y;
  return positioned.map((node) => ({
    ...node,
    position: {
      x: node.position.x - offsetX,
      y: node.position.y - offsetY,
    },
  }));
}
