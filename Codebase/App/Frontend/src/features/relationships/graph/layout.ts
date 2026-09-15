import dagre from "@dagrejs/dagre";
import type { Edge, Node } from "@xyflow/react";

export const NODE_WIDTH = 224;
export const NODE_HEIGHT = 82;

export type ConnectionRegion =
  | "origin"
  | "maternal"
  | "paternal"
  | "siblings"
  | "partner"
  | "children"
  | "external"
  | "family"
  | "path"
  | "target";

type PositionedNode = Node & {
  data: {
    region?: ConnectionRegion;
    /** A route-only node can request a deliberately stable lane. */
    preferredPosition?: { x: number; y: number };
  };
};

const SECTOR_SLOTS: Record<Exclude<ConnectionRegion, "origin">, Array<{ x: number; y: number }>> = {
  // These are card top-left coordinates around the stable FROM card at 0,0.
  // Their placement is deliberately radial/contextual, not a generational rank.
  maternal: [
    { x: -500, y: -300 }, { x: -745, y: -190 }, { x: -455, y: -95 },
    { x: -730, y: 5 }, { x: -470, y: 105 },
  ],
  paternal: [
    { x: 500, y: -300 }, { x: 745, y: -190 }, { x: 455, y: -95 },
    { x: 730, y: 5 }, { x: 470, y: 105 },
  ],
  siblings: [
    { x: -410, y: 30 }, { x: -525, y: 175 }, { x: -355, y: 220 },
    { x: -600, y: 315 }, { x: -340, y: 365 },
  ],
  partner: [
    { x: 345, y: 30 }, { x: 475, y: 175 }, { x: 305, y: 220 },
  ],
  children: [
    { x: -155, y: 295 }, { x: 120, y: 295 }, { x: -285, y: 430 },
    { x: -10, y: 445 }, { x: 265, y: 430 },
  ],
  // External links sit below and around FROM; they do not form a boxed branch.
  external: [
    { x: -650, y: 350 }, { x: -405, y: 475 }, { x: -135, y: 555 },
    { x: 145, y: 555 }, { x: 415, y: 475 }, { x: 660, y: 350 },
    { x: -670, y: 585 }, { x: 665, y: 585 }, { x: -395, y: 680 },
    { x: 390, y: 680 },
  ],
  family: [
    { x: -240, y: -165 }, { x: 240, y: -165 }, { x: -620, y: 225 },
    { x: 620, y: 225 }, { x: -115, y: 565 }, { x: 150, y: 565 },
  ],
  // A small neutral path lane is only used for route-only intermediates. The
  // normal direct-context positions are retained while TO changes.
  path: [
    { x: -165, y: -405 }, { x: 150, y: -405 }, { x: -190, y: 620 },
    { x: 175, y: 620 }, { x: -475, y: 575 }, { x: 455, y: 575 },
  ],
  target: [
    { x: -520, y: 650 }, { x: 520, y: 650 }, { x: 0, y: 780 },
    { x: 0, y: -470 }, { x: -650, y: 260 }, { x: 650, y: 260 },
  ],
};

function slotFor(region: ConnectionRegion, index: number): { x: number; y: number } {
  if (region === "origin") return { x: 0, y: 0 };
  const slots = SECTOR_SLOTS[region];
  if (index < slots.length) return slots[index];
  // Overflow stays in the same contextual sector rather than turning into a
  // graph-wide generation row. The modest offset keeps its edges readable.
  const base = slots[index % slots.length];
  const ring = Math.floor(index / slots.length);
  return {
    x: base.x + (base.x < 0 ? -1 : 1) * ring * 130,
    y: base.y + ring * 115,
  };
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
    const preferred = typed.data.preferredPosition;
    if (existing) {
      occupied.push(existing);
      return { ...node, position: existing };
    }

    let index = regionCounts.get(region) ?? 0;
    let position = preferred ?? slotFor(region, index);
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
