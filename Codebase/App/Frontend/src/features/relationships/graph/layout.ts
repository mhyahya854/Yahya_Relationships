import dagre from "@dagrejs/dagre";
import type { Edge, Node } from "@xyflow/react";

export const NODE_WIDTH = 205;
export const NODE_HEIGHT = 64;

/**
 * Deterministic hierarchical layout. Input nodes/edges are sorted before
 * layout so small graph changes produce stable positions.
 */
export function layoutGraph(
  nodes: Node[],
  edges: Edge[],
  direction: "TB" | "LR" = "TB",
): Node[] {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({ rankdir: direction, nodesep: 70, ranksep: 80, marginx: 30, marginy: 30 });

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

  return sortedNodes.map((node) => {
    const position = graph.node(node.id);
    return {
      ...node,
      position: { x: position.x - NODE_WIDTH / 2, y: position.y - NODE_HEIGHT / 2 },
    };
  });
}
