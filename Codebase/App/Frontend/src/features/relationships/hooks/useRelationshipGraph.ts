import { useCallback, useRef, useState } from "react";
import { relationshipsApi } from "../api";
import type {
  ExpansionFilter,
  GraphEdgeDto,
  GraphNodeDto,
  RelationshipPath,
} from "../types";
import { allFilters, mergeNeighbors, removeExpansion } from "../graph/graphState";

interface ModelState {
  nodes: GraphNodeDto[];
  edges: GraphEdgeDto[];
  expansions: Record<string, { nodes: string[]; edges: string[] }>;
  pinned: string[];
  overlayNodes: GraphNodeDto[];
  overlayEdges: GraphEdgeDto[];
}

const EMPTY: ModelState = {
  nodes: [],
  edges: [],
  expansions: {},
  pinned: [],
  overlayNodes: [],
  overlayEdges: [],
};

function expansionKey(personId: string, filter: ExpansionFilter): string {
  return `${personId}:${filter}`;
}

function applyExpansion(
  state: ModelState,
  key: string,
  payload: { nodes: GraphNodeDto[]; edges: GraphEdgeDto[] },
): ModelState {
  const nodesById = new Map(state.nodes.map((node) => [node.id, node]));
  const edgesById = new Map(state.edges.map((edge) => [edge.id, edge]));
  const added = mergeNeighbors({ nodes: nodesById, edges: edgesById }, payload);
  const expansions = { ...state.expansions };
  expansions[key] = { nodes: added.addedNodes, edges: added.addedEdges };
  return {
    ...state,
    nodes: [...nodesById.values()],
    edges: [...edgesById.values()],
    expansions,
  };
}

function removeExpansionFromState(state: ModelState, key: string): ModelState {
  const nodesById = new Map(state.nodes.map((node) => [node.id, node]));
  const edgesById = new Map(state.edges.map((edge) => [edge.id, edge]));
  const expansions = { ...state.expansions };
  const contribution = expansions[key];
  if (!contribution) return state;
  removeExpansion(expansions, key, {
    nodes: nodesById,
    edges: edgesById,
    pinned: new Set(state.pinned),
  });
  return {
    ...state,
    nodes: [...nodesById.values()],
    edges: [...edgesById.values()],
    expansions,
  };
}

export function useRelationshipGraph() {
  const [state, setState] = useState<ModelState>(EMPTY);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const requestToken = useRef(0);

  const reset = useCallback(async (personId: string) => {
    const token = ++requestToken.current;
    setLoading(true);
    setError(null);
    let next: ModelState = {
      nodes: [],
      edges: [],
      expansions: {},
      pinned: [personId],
      overlayNodes: [],
      overlayEdges: [],
    };
    // Perspective person is always present.
    next.nodes = [
      {
        id: personId,
        name: personId,
        is_perspective: true,
      },
    ];
    setState(next);
    const filters = allFilters();
    try {
      for (const filter of filters) {
        const single = await relationshipsApi.neighbors(
          personId,
          personId,
          [filter],
        );
        if (token !== requestToken.current) return;
        next = applyExpansion(next, expansionKey(personId, filter), single);
      }
      if (token === requestToken.current) setState(next);
    } catch (err) {
      if (token === requestToken.current) setError(err);
    } finally {
      if (token === requestToken.current) setLoading(false);
    }
  }, []);

  const stateRef = useRef(state);
  stateRef.current = state;

  const toggleExpansion = useCallback(
    async (personId: string, perspectiveId: string, filter: ExpansionFilter) => {
      const token = requestToken.current;
      const key = expansionKey(personId, filter);
      const exists = Boolean(stateRef.current.expansions[key]);
      setLoading(true);
      setError(null);
      try {
        if (exists) {
          setState((current) => removeExpansionFromState(current, key));
        } else {
          const payload = await relationshipsApi.neighbors(
            personId,
            perspectiveId,
            [filter],
          );
          if (token !== requestToken.current) return;
          setState((current) =>
            applyExpansion(current, key, {
              nodes: payload.nodes.map((node) => ({
                ...node,
                is_perspective: node.id === perspectiveId,
              })),
              edges: payload.edges,
            }),
          );
        }
      } catch (err) {
        if (token === requestToken.current) setError(err);
      } finally {
        if (token === requestToken.current) setLoading(false);
      }
    },
    [],
  );

  const ensureVisible = useCallback((person: GraphNodeDto) => {
    setState((current) => {
      if (current.nodes.some((node) => node.id === person.id)) {
        const nodes = current.nodes.map((node) =>
          node.id === person.id ? { ...node, ...person } : node,
        );
        return { ...current, nodes };
      }
      return {
        ...current,
        nodes: [...current.nodes, { ...person, is_virtual: false }],
        pinned: current.pinned.includes(person.id)
          ? current.pinned
          : [...current.pinned, person.id],
      };
    });
  }, []);

  const refreshPerspectiveLabels = useCallback(async (perspectiveId: string) => {
    try {
      const result = await relationshipsApi.fromPerspective(perspectiveId);
      const labelById = new Map<string, { en?: string; ur?: string | null }>();
      for (const row of result.relationships) {
        const first = row.primary[0];
        if (first) {
          labelById.set(row.target.id, {
            en: first.label_en,
            ur: first.label_ur,
          });
        }
      }
      setState((current) => ({
        ...current,
        nodes: current.nodes.map((node) => {
          const relation = labelById.get(node.id);
          if (!relation) return node;
          return {
            ...node,
            relation_label_en: relation.en,
            relation_label_ur: relation.ur,
          };
        }),
      }));
    } catch {
      // Labels are cosmetic; graph remains usable.
    }
  }, []);

  const focusPath = useCallback((path: RelationshipPath) => {
    setState((current) => {
      const overlayNodes = [...current.overlayNodes];
      const overlayEdges = [...current.overlayEdges];
      const visibleNodeIds = new Set([
        ...current.nodes.map((node) => node.id),
        ...overlayNodes.map((node) => node.id),
      ]);
      const visibleEdgePairs = new Set(
        [...current.edges, ...overlayEdges].map(
          (edge) => [edge.source, edge.target].sort().join("::"),
        ),
      );
      for (const node of path.nodes) {
        if (!visibleNodeIds.has(node.id)) {
          overlayNodes.push({
            id: node.id,
            name: node.name,
            is_virtual: node.is_virtual ?? false,
            relation_label_en: null,
            relation_label_ur: null,
          });
        }
      }
      for (const edge of path.edges) {
        const pair = [edge.from, edge.to].sort().join("::");
        if (!visibleEdgePairs.has(pair)) {
          overlayEdges.push({
            id: `overlay:${edge.from}:${edge.to}:${edge.type}`,
            source: edge.from,
            target: edge.to,
            domain: path.domain,
            type: edge.type,
            subtype: edge.subtype,
          });
        }
      }
      return { ...current, overlayNodes, overlayEdges };
    });
  }, []);

  const exitPath = useCallback(() => {
    setState((current) => ({
      ...current,
      overlayNodes: [],
      overlayEdges: [],
    }));
  }, []);

  return {
    nodes: state.nodes,
    edges: state.edges,
    overlayNodes: state.overlayNodes,
    overlayEdges: state.overlayEdges,
    pinned: state.pinned,
    expansions: state.expansions,
    loading,
    error,
    reset,
    toggleExpansion,
    ensureVisible,
    refreshPerspectiveLabels,
    focusPath,
    exitPath,
  };
}
