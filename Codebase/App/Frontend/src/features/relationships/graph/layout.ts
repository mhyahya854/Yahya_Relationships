import dagre from "@dagrejs/dagre";
import type { Edge, Node } from "@xyflow/react";

export const NODE_WIDTH = 188;
export const NODE_HEIGHT = 72;

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
