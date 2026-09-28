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
    /** Active routes update their own lane without disturbing direct context. */
    forcePreferredPosition?: boolean;
  };
};

const SECTOR_SLOTS: Record<Exclude<ConnectionRegion, "origin">, Array<{ x: number; y: number }>> = {
  // These are card top-left coordinates around the stable FROM card at 0,0.
  // Their placement is deliberately radial/contextual, not a generational rank.
  maternal: [
    { x: -330, y: -205 }, { x: -470, y: -115 }, { x: -345, y: -65 },
    { x: -445, y: 15 }, { x: -330, y: 82 },
  ],
  paternal: [
    { x: 330, y: -205 }, { x: 470, y: -115 }, { x: 345, y: -65 },
    { x: 445, y: 15 }, { x: 330, y: 82 },
  ],
  siblings: [
    { x: -285, y: 12 }, { x: -390, y: 128 }, { x: -250, y: 168 },
    { x: -455, y: 250 }, { x: -235, y: 280 },
  ],
  partner: [
    { x: 265, y: 12 }, { x: 375, y: 128 }, { x: 225, y: 168 },
  ],
  children: [
    { x: -135, y: 225 }, { x: 105, y: 225 }, { x: -245, y: 335 },
    { x: -10, y: 350 }, { x: 225, y: 335 },
  ],
  // External links sit below and around FROM; they do not form a boxed branch.
  external: [
    { x: -420, y: 230 }, { x: -250, y: 305 }, { x: -72, y: 350 },
    { x: 115, y: 350 }, { x: 290, y: 305 }, { x: 440, y: 230 },
    { x: -355, y: 420 }, { x: 365, y: 420 }, { x: -120, y: 472 },
    { x: 155, y: 472 },
  ],
  family: [
    { x: -185, y: -135 }, { x: 185, y: -135 }, { x: -390, y: 172 },
    { x: 390, y: 172 }, { x: -105, y: 400 }, { x: 135, y: 400 },
  ],
  // A small neutral path lane is only used for route-only intermediates. The
  // normal direct-context positions are retained while TO changes.
  path: [
    { x: -135, y: -310 }, { x: 125, y: -310 }, { x: -150, y: 455 },
    { x: 140, y: 455 }, { x: -365, y: 405 }, { x: 345, y: 405 },
  ],
  target: [
    { x: -360, y: 430 }, { x: 360, y: 430 }, { x: 0, y: 530 },
    { x: 0, y: -360 }, { x: -460, y: 210 }, { x: 460, y: 210 },
  ],
};

// A six-person world should not inherit the footprint of a busy owner view.
// These slots preserve the same semantic compass points as SECTOR_SLOTS, but
// keep a small perspective conversational and wholly inside the canvas.
const COMPACT_SECTOR_SLOTS: Record<Exclude<ConnectionRegion, "origin">, Array<{ x: number; y: number }>> = {
  maternal: [
    { x: -250, y: -160 }, { x: -395, y: -45 }, { x: -250, y: -15 },
    { x: -355, y: 55 }, { x: -245, y: 115 },
  ],
  paternal: [
    { x: 250, y: -160 }, { x: 395, y: -45 }, { x: 250, y: -15 },
    { x: 355, y: 55 }, { x: 245, y: 115 },
  ],
  siblings: [
    { x: -275, y: 85 }, { x: -430, y: 175 }, { x: -225, y: 235 },
    { x: -395, y: 285 }, { x: -210, y: 335 },
  ],
  partner: [
    { x: 275, y: 85 }, { x: 410, y: 175 }, { x: 220, y: 235 },
  ],
  children: [
    { x: -115, y: 215 }, { x: 135, y: 215 }, { x: -245, y: 305 },
    { x: 10, y: 330 }, { x: 240, y: 305 },
  ],
  external: [
    { x: -360, y: 245 }, { x: -220, y: 350 }, { x: 25, y: 385 },
    { x: 265, y: 350 }, { x: 390, y: 245 }, { x: -385, y: 390 },
  ],
  family: [
    { x: -200, y: -100 }, { x: 200, y: -100 }, { x: -340, y: 160 },
    { x: 340, y: 160 }, { x: -80, y: 365 }, { x: 160, y: 365 },
  ],
  path: [
    { x: -105, y: -245 }, { x: 105, y: -245 }, { x: -110, y: 350 },
    { x: 110, y: 350 }, { x: -300, y: 315 }, { x: 285, y: 315 },
  ],
  target: [
    { x: -260, y: 300 }, { x: 260, y: 300 }, { x: 0, y: 385 },
    { x: 0, y: -285 }, { x: -365, y: 165 }, { x: 365, y: 165 },
  ],
};

function layoutScaleFor(nodeCount: number): number {
  // Small direct worlds should feel close and conversational. Dense worlds get
  // just enough room to avoid overlap, rather than inheriting a huge fixed
  // canvas designed for the largest fixture.
  if (nodeCount <= 3) return 0.5;
  if (nodeCount <= 6) return 0.6;
  if (nodeCount <= 9) return 0.82;
  if (nodeCount <= 15) return 0.91;
  return 1;
}

function slotFor(
  region: ConnectionRegion,
  index: number,
  scale: number,
  slotsByRegion: typeof SECTOR_SLOTS = SECTOR_SLOTS,
): { x: number; y: number } {
  if (region === "origin") return { x: 0, y: 0 };
  const slots = slotsByRegion[region];
  if (index < slots.length) {
    return { x: slots[index].x * scale, y: slots[index].y * scale };
  }
  // Overflow stays in the same contextual sector rather than turning into a
  // graph-wide generation row. The modest offset keeps its edges readable.
  const base = slots[index % slots.length];
  const ring = Math.floor(index / slots.length);
  return {
    x: (base.x + (base.x < 0 ? -1 : 1) * ring * 104) * scale,
    y: (base.y + ring * 92) * scale,
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
  // Stable direct-context cards must reserve their space before route-only
  // nodes are packed. Sorting route nodes alphabetically first used to let an
  // intermediate temporarily claim the same slot as a later direct card.
  const nodeIds = new Set(nodes.map((node) => node.id));
  const forcedIds = new Set(
    nodes
      .filter((node) => (node as PositionedNode).data.forcePreferredPosition)
      .map((node) => node.id),
  );
  const occupied: Array<{ x: number; y: number }> = previousPositions
    ? [...previousPositions.entries()]
      .filter(([id]) => nodeIds.has(id) && !forcedIds.has(id))
      .map(([, position]) => position)
    : [];
  const regionCounts = new Map<ConnectionRegion, number>();
  const sorted = [...nodes].sort((a, b) => a.id.localeCompare(b.id));
  const nodeCount = Math.max(0, nodes.length - (centerId ? 1 : 0));
  const usesCompactSlots = nodeCount <= 6;
  const slotsByRegion = usesCompactSlots ? COMPACT_SECTOR_SLOTS : SECTOR_SLOTS;
  const scale = usesCompactSlots
    ? (nodeCount <= 3 ? 0.72 : 1)
    : layoutScaleFor(nodeCount);

  return sorted.map((node) => {
    const typed = node as PositionedNode;
    const region: ConnectionRegion = node.id === centerId
      ? "origin"
      : typed.data.region ?? "family";
    const existing = previousPositions?.get(node.id);
    const preferred = typed.data.preferredPosition;
    if (preferred && typed.data.forcePreferredPosition) {
      // Route-only cards can update as the user selects a different canonical
      // path. Their direct-context neighbours retain their stored positions.
      const routeOffsets = [{ x: 0, y: 0 }];
      for (let ring = 1; ring <= 3; ring += 1) {
        for (let row = -ring; row <= ring; row += 1) {
          for (let column = -ring; column <= ring; column += 1) {
            if (Math.max(Math.abs(row), Math.abs(column)) !== ring) continue;
            routeOffsets.push({ x: column * 132, y: row * 108 });
          }
        }
      }
      // Preserve the intended route lane before trying a wholesale new
      // quadrant. Side-by-side openings and then lower openings keep a long
      // route in the visible immediate-context envelope; the previous
      // row-major search chose the upper-left corner first, which could push
      // a perfectly valid intermediate card off the top of the canvas.
      routeOffsets.sort((left, right) => {
        const distance = left.x ** 2 + left.y ** 2 - (right.x ** 2 + right.y ** 2);
        if (distance) return distance;
        const vertical = Math.abs(left.y) - Math.abs(right.y);
        if (vertical) return vertical;
        if (left.y !== right.y) return right.y - left.y;
        const horizontal = Math.abs(left.x) - Math.abs(right.x);
        if (horizontal) return horizontal;
        return left.x - right.x;
      });
      const clampRoutePoint = (point: { x: number; y: number }) => ({
        x: Math.max(-560, Math.min(560, point.x)),
        y: Math.max(-220, Math.min(590, point.y)),
      });
      const position = routeOffsets
        .map((offset) => clampRoutePoint({ x: preferred.x + offset.x, y: preferred.y + offset.y }))
        .find((candidate) => !overlaps(candidate, occupied)) ?? clampRoutePoint(preferred);
      occupied.push(position);
      return { ...node, position };
    }
    if (existing) {
      return { ...node, position: existing };
    }

    let index = regionCounts.get(region) ?? 0;
    let position = preferred ?? slotFor(region, index, scale, slotsByRegion);
    while (overlaps(position, occupied)) {
      index += 1;
      position = slotFor(region, index, scale, slotsByRegion);
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
