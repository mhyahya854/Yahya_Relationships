import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type DragEvent } from "react";
import {
  Background,
  BackgroundVariant,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api } from "../api";
import { CompareModal, JournalModal } from "../components/PersonDetail";
import { Avatar, Button, ErrorNote, Icon, Modal, PersonSearch } from "../components/ui";
import { usePerspective } from "../state";
import type { Person } from "../types";
import { GraphDock } from "../features/relationships/components/GraphDock";
import { PersonInfoDrawer } from "../features/relationships/components/PersonInfoDrawer";
import { PersonNode } from "../features/relationships/components/PersonNode";
import {
  CONNECTIONS_PERSON_DRAG_TYPE,
  RelationshipBuilder,
  type ImmediateConnection,
} from "../features/relationships/components/RelationshipBuilder";
import { RelationshipTargetCard } from "../features/relationships/components/RelationshipTargetCard";
import { edgeVisual } from "../features/relationships/graph/edgeStyles";
import { layoutConnectionGraph, NODE_HEIGHT, NODE_WIDTH } from "../features/relationships/graph/layout";
import { useKeyboardNavigation } from "../features/relationships/hooks/useKeyboardNavigation";
import { useRelationshipGraph } from "../features/relationships/hooks/useRelationshipGraph";
import type { GraphEdgeDto, GraphNodeDto, RelationshipPath } from "../features/relationships/types";

const nodeTypes = { person: PersonNode };

function pathPairKey(first: string, second: string): string {
  return [first, second].sort().join("::");
}

interface ActivePathEdge {
  sides: Set<string>;
  domains: Set<RelationshipPath["domain"]>;
}

function pathEdgeDetails(paths: RelationshipPath[]): Map<string, ActivePathEdge> {
  const details = new Map<string, ActivePathEdge>();
  for (const path of paths) {
    for (const edge of path.edges) {
      const key = pathPairKey(edge.from, edge.to);
      const visual = details.get(key) ?? { sides: new Set<string>(), domains: new Set<RelationshipPath["domain"]>() };
      if (path.side) visual.sides.add(path.side);
      visual.domains.add(path.domain);
      details.set(key, visual);
    }
  }
  return details;
}

function buildFlowEdges(
  edgeDtos: GraphEdgeDto[],
  activePaths: RelationshipPath[],
  activeEdges: Map<string, ActivePathEdge>,
  availableEdges: Map<string, ActivePathEdge>,
  positions: ReadonlyMap<string, { x: number; y: number }>,
  hasTargets: boolean,
): Edge[] {
  const hasActivePaths = activePaths.length > 0;
  const handleFor = (from: { x: number; y: number }, to: { x: number; y: number }, prefix: "source" | "target") => {
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    let direction: "top" | "right" | "bottom" | "left";
    if (Math.abs(dx) > Math.abs(dy)) direction = dx >= 0 ? "right" : "left";
    else direction = dy >= 0 ? "bottom" : "top";
    if (prefix === "target") {
      direction = direction === "top" ? "bottom"
        : direction === "bottom" ? "top"
          : direction === "left" ? "right" : "left";
    }
    return `${prefix}-${direction}`;
  };
  return edgeDtos.map((dto) => {
    const visual = edgeVisual(dto);
    const activeDetail = activeEdges.get(pathPairKey(dto.source, dto.target));
    const availableDetail = availableEdges.get(pathPairKey(dto.source, dto.target));
    const pathDetail = activeDetail ?? availableDetail;
    const isActivePath = Boolean(activeDetail);
    const isAvailablePath = Boolean(availableDetail);
    const pathStroke = pathDetail?.sides.size === 1 && pathDetail.sides.has("maternal")
      ? "var(--maternal)"
      : pathDetail?.sides.size === 1 && pathDetail.sides.has("paternal")
        ? "var(--paternal)"
        : pathDetail?.domains.has("general")
          ? "var(--general-line)"
          : "var(--accent-primary)";
    const source = positions.get(dto.source);
    const target = positions.get(dto.target);
    const sourceCenter = source && { x: source.x + 112, y: source.y + 41 };
    const targetCenter = target && { x: target.x + 112, y: target.y + 41 };
    const sourceHandle = sourceCenter && targetCenter ? handleFor(sourceCenter, targetCenter, "source") : undefined;
    const targetHandle = sourceCenter && targetCenter ? handleFor(targetCenter, sourceCenter, "target") : undefined;
    return {
      id: dto.id,
      source: dto.source,
      target: dto.target,
      // Direct chords avoid the hard backtracking that makes long family
      // routes read like a circuit diagram. Cards layer above the route, so a
      // connector cannot compete with a person's information.
      type: "straight",
      sourceHandle,
      targetHandle,
      style: {
        stroke: isAvailablePath
          ? (isActivePath ? `color-mix(in srgb, ${pathStroke} 78%, white)` : pathStroke)
          : visual.stroke,
        strokeWidth: isActivePath ? 1.4 : isAvailablePath ? 0.95 : Math.min(visual.strokeWidth, 0.95),
        strokeDasharray: isActivePath ? visual.strokeDasharray : isAvailablePath ? "3 4" : visual.strokeDasharray,
        opacity: isActivePath ? 0.88 : isAvailablePath ? 0.34 : hasTargets ? 0.06 : 0.52,
      },
      className: [
        visual.className,
        isActivePath ? "rf-edge-path rf-edge-path-active" : "",
        isAvailablePath && !isActivePath ? "rf-edge-path rf-edge-path-available" : "",
        hasActivePaths && !isAvailablePath ? "rf-edge-dim" : "",
      ].filter(Boolean).join(" "),
    };
  });
}

function connectionRegion(
  node: GraphNodeDto,
  edges: GraphEdgeDto[],
  fromId: string | null,
  isPathIntermediate: boolean,
  isTo: boolean,
): "origin" | "maternal" | "paternal" | "siblings" | "partner" | "children" | "external" | "family" | "path" | "target" {
  if (node.id === fromId) return "origin";
  if (isPathIntermediate) return "path";
  if (isTo) return "target";
  const label = (node.relation_label_en ?? "").toLowerCase();
  if (/maternal|mother|mami|mama/.test(label)) return "maternal";
  if (/paternal|father|chachi|chacha/.test(label)) return "paternal";
  if (edges.some((edge) => (edge.source === node.id || edge.target === node.id) && edge.domain === "general")) {
    return "external";
  }
  if (/husband|wife|spouse|partner/.test(label)) return "partner";
  if (/son|daughter|child/.test(label)) return "children";
  if (/brother|sister|sibling/.test(label)) return "siblings";
  return "family";
}

interface NavigationProps {
  initialTargetId?: string | null;
  onTargetChange?: (personId: string | null) => void;
  onTargetUnavailable?: (personId: string) => void;
  onNavigateToProfile?: (personId: string) => void;
  onNavigateToFamily?: (personId: string) => void;
}

interface ImmediateContextSnapshot {
  perspectiveId: string;
  nodes: GraphNodeDto[];
  edges: GraphEdgeDto[];
}

function RelationshipsContent({
  initialTargetId,
  onTargetChange,
  onTargetUnavailable,
  onNavigateToProfile,
  onNavigateToFamily,
}: NavigationProps) {
  const { perspectiveId, perspectivePerson, defaultId, setPerspective, returnToDefault } = usePerspective();
  const graph = useRelationshipGraph();
  // A new FROM is allowed to render only its own graph snapshot. Otherwise a
  // stale frame can reserve owner positions before reset completes and make a
  // small alternate perspective inherit a sprawling composition.
  const graphMatchesPerspective = graph.perspectiveId === perspectiveId;
  const graphNodes = graphMatchesPerspective ? graph.nodes : [];
  const graphEdges = graphMatchesPerspective ? graph.edges : [];
  const graphOverlayNodes = graphMatchesPerspective ? graph.overlayNodes : [];
  const graphOverlayEdges = graphMatchesPerspective ? graph.overlayEdges : [];
  const { fitView, zoomIn, zoomOut } = useReactFlow();
  const [people, setPeople] = useState<Person[]>([]);
  const [peopleLoaded, setPeopleLoaded] = useState(false);
  const [selected, setSelected] = useState<Person | null>(null);
  const [selectedTargets, setSelectedTargets] = useState<Person[]>([]);
  const [immediateContext, setImmediateContext] = useState<ImmediateContextSnapshot | null>(null);
  const [highlightedPathsByTarget, setHighlightedPathsByTarget] = useState<Record<string, RelationshipPath[]>>({});
  const [availablePathsByTarget, setAvailablePathsByTarget] = useState<Record<string, RelationshipPath[]>>({});
  const [relationshipError, setRelationshipError] = useState<unknown>(null);
  const [infoPerson, setInfoPerson] = useState<Person | null>(null);
  const [journalFor, setJournalFor] = useState<Person | null>(null);
  const [comparePicker, setComparePicker] = useState(false);
  const [compareTarget, setCompareTarget] = useState<Person | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchSelection, setSearchSelection] = useState<Person | null>(null);
  const [immersive, setImmersive] = useState(false);
  const [nativeFullscreen, setNativeFullscreen] = useState(false);
  const [zoomPercent, setZoomPercent] = useState(100);
  const [clearPathsVersion, setClearPathsVersion] = useState(0);
  const graphAreaRef = useRef<HTMLDivElement | null>(null);
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const appliedInitialTargetRef = useRef<string | null>(null);
  const positionStoreRef = useRef(new Map<string, { x: number; y: number }>());
  const fittedPerspectiveRef = useRef<string | null>(null);

  const loadPeople = useCallback(async () => {
    try {
      const response = await api.people.list();
      setPeople(response.people);
    } catch (error) {
      setRelationshipError(error);
    } finally {
      setPeopleLoaded(true);
    }
  }, []);

  useEffect(() => { void loadPeople(); }, [loadPeople]);

  useEffect(() => {
    if (!perspectiveId) return;
    setHighlightedPathsByTarget({});
    setAvailablePathsByTarget({});
    setSelectedTargets((current) => current.filter((person) => person.id !== perspectiveId));
    setSelected((current) => current?.id === perspectiveId ? null : current);
    setImmediateContext(null);
    positionStoreRef.current.clear();
    fittedPerspectiveRef.current = null;
    void graph.reset(perspectiveId);
    // The perspective is FROM; it is the only operation that resets the base graph.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [perspectiveId]);

  // The immediate graph is the visual context contract for a Connections
  // session. Preserve that direct-neighbour snapshot while path requests add
  // or replace their overlay nodes, so an asynchronous route response can
  // never make surrounding context disappear from the canvas.
  useEffect(() => {
    if (!perspectiveId || !graphMatchesPerspective || graph.loading || selectedTargets.length || !graphNodes.length) return;
    setImmediateContext({
      perspectiveId,
      nodes: graphNodes,
      edges: graphEdges,
    });
  }, [graphEdges, graphMatchesPerspective, graph.loading, graphNodes, perspectiveId, selectedTargets.length]);

  const personOfNode = useCallback(
    (personId: string) => people.find((person) => person.id === personId),
    [people],
  );

  const selectPerson = useCallback((person: Person) => {
    setSelected(person);
    setRelationshipError(null);
    graph.ensureVisible({
      id: person.id,
      name: person.name,
      is_perspective: person.id === perspectiveId,
    });
  }, [graph, perspectiveId]);

  const addTo = useCallback((person: Person) => {
    if (person.id === perspectiveId) return;
    selectPerson(person);
    // Search may have revealed a distant person as a temporary neutral card.
    // Once it becomes TO, give that new target its deliberate route-sector
    // slot; immediate neighbours retain their stable context coordinates.
    const isImmediate = graphEdges.some(
      (edge) => (edge.source === perspectiveId && edge.target === person.id)
        || (edge.target === perspectiveId && edge.source === person.id),
    );
    if (!isImmediate) positionStoreRef.current.delete(person.id);
    setSelectedTargets((current) => current.some((target) => target.id === person.id)
      ? current
      : [...current, person]);
    onTargetChange?.(person.id);
  }, [graphEdges, onTargetChange, perspectiveId, selectPerson]);

  const setFrom = useCallback((person: Person) => {
    if (person.id === perspectiveId) return;
    setSelected(person);
    setInfoPerson(null);
    void setPerspective(person.id);
  }, [perspectiveId, setPerspective]);

  const removeTarget = useCallback((personId: string) => {
    setSelectedTargets((current) => {
      const next = current.filter((person) => person.id !== personId);
      onTargetChange?.(next[0]?.id ?? null);
      return next;
    });
    setSelected((current) => current?.id === personId ? null : current);
    setHighlightedPathsByTarget((current) => {
      if (!(personId in current)) return current;
      const next = { ...current };
      delete next[personId];
      return next;
    });
    setAvailablePathsByTarget((current) => {
      if (!(personId in current)) return current;
      const next = { ...current };
      delete next[personId];
      return next;
    });
  }, [onTargetChange]);

  const clearTargets = useCallback(() => {
    setSelectedTargets([]);
    setHighlightedPathsByTarget({});
    setAvailablePathsByTarget({});
    onTargetChange?.(null);
  }, [onTargetChange]);

  const handleDropPerson = useCallback((zone: "from" | "to", personId: string) => {
    const person = personOfNode(personId);
    if (!person) return;
    if (zone === "from") setFrom(person);
    else addTo(person);
  }, [addTo, personOfNode, setFrom]);

  useEffect(() => {
    if (!peopleLoaded) return;
    if (!initialTargetId) {
      appliedInitialTargetRef.current = null;
      return;
    }
    if (appliedInitialTargetRef.current === initialTargetId) return;
    appliedInitialTargetRef.current = initialTargetId;
    const match = people.find((person) => person.id === initialTargetId);
    if (match) addTo(match);
    else {
      setRelationshipError(new Error("That relationship target is no longer available in this Data Root."));
      onTargetUnavailable?.(initialTargetId);
    }
  }, [addTo, initialTargetId, onTargetUnavailable, people, peopleLoaded]);

  const highlightedPaths = useMemo(
    () => Object.values(highlightedPathsByTarget).flat(),
    [highlightedPathsByTarget],
  );
  const availablePaths = useMemo(
    () => Object.values(availablePathsByTarget).flat(),
    [availablePathsByTarget],
  );

  useEffect(() => {
    if (!graphMatchesPerspective) return;
    if (availablePaths.length) graph.focusPaths(availablePaths);
    else graph.exitPath();
  }, [availablePaths, graph.exitPath, graph.focusPaths, graphMatchesPerspective]);

  const visibleNodeDtos = useMemo(() => {
    const nodes = new Map<string, GraphNodeDto>();
    const immediateNodes = immediateContext?.perspectiveId === perspectiveId
      ? immediateContext.nodes
      : [];
    for (const node of [...immediateNodes, ...graphNodes, ...graphOverlayNodes]) nodes.set(node.id, node);
    return [...nodes.values()];
  }, [graphNodes, graphOverlayNodes, immediateContext, perspectiveId]);
  const availableNodeIds = useMemo(
    () => new Set(availablePaths.flatMap((path) => path.nodes.map((node) => node.id))),
    [availablePaths],
  );
  const highlightedEdges = useMemo(() => pathEdgeDetails(highlightedPaths), [highlightedPaths]);
  const availableEdges = useMemo(() => pathEdgeDetails(availablePaths), [availablePaths]);
  const targetIds = useMemo(() => new Set(selectedTargets.map((person) => person.id)), [selectedTargets]);
  const visibleEdgeDtos = useMemo(() => {
    const edges = new Map<string, GraphEdgeDto>();
    const immediateEdges = immediateContext?.perspectiveId === perspectiveId
      ? immediateContext.edges
      : [];
    for (const edge of [...immediateEdges, ...graphEdges, ...graphOverlayEdges]) edges.set(edge.id, edge);
    // The base canvas deliberately shows the direct immediate-star only.
    // Relationships between two neighbours are canonical facts, but making
    // them visible here turns a connection explorer back into a family tree.
    // Route segments reappear only when a selected canonical path requires
    // them, so no path truth is discarded.
    return [...edges.values()].filter((edge) => {
      const directFrom = edge.source === perspectiveId || edge.target === perspectiveId;
      return directFrom || availableEdges.has(pathPairKey(edge.source, edge.target));
    });
  }, [availableEdges, graphEdges, graphOverlayEdges, immediateContext, perspectiveId]);

  const routePlacementById = useMemo(() => {
    type RouteCandidate = {
      id: string;
      targetIds: Set<string>;
      proposed: Array<{ x: number; y: number }>;
    };
    const baseNodeIds = new Set<string>(perspectiveId ? [perspectiveId] : []);
    for (const edge of graphEdges) {
      if (edge.source === perspectiveId) baseNodeIds.add(edge.target);
      if (edge.target === perspectiveId) baseNodeIds.add(edge.source);
    }
    const candidates = new Map<string, RouteCandidate>();
    const targetSlots = [
      { x: 0, y: 590 }, { x: -440, y: 500 }, { x: 440, y: 500 },
      { x: 0, y: -340 },
    ];
    const remoteTargets = selectedTargets.filter((person) => !baseNodeIds.has(person.id));
    const targetPosition = new Map(
      remoteTargets.map((person, index) => [person.id, targetSlots[index % targetSlots.length]]),
    );
    for (const [pathIndex, path] of highlightedPaths.entries()) {
      const pathTarget = path.nodes[path.nodes.length - 1]?.id;
      if (!pathTarget || !targetPosition.has(pathTarget)) continue;
      const target = targetPosition.get(pathTarget)!;
      let anchor = { x: 0, y: 0 };
      let anchorIndex = 0;
      const laneSign = path.side === "maternal" ? 1 : path.side === "paternal" ? -1 : pathIndex % 2 === 0 ? 1 : -1;
      path.nodes.forEach((node, index) => {
        if (index === 0) return;
        if (baseNodeIds.has(node.id)) {
          anchor = positionStoreRef.current.get(node.id) ?? anchor;
          anchorIndex = index;
          return;
        }
        const span = Math.max(1, path.nodes.length - 1 - anchorIndex);
        const ratio = (index - anchorIndex) / span;
        const dx = target.x - anchor.x;
        const dy = target.y - anchor.y;
        const distance = Math.max(1, Math.hypot(dx, dy));
        // A shallow contextual arc keeps long route-only chains beside the
        // immediate world rather than running diagonally through its cards.
        const laneOffset = Math.sin(Math.PI * ratio) * 112 * laneSign;
        const current = candidates.get(node.id) ?? {
          id: node.id,
          targetIds: new Set<string>(),
          proposed: [],
        };
        current.targetIds.add(pathTarget);
        current.proposed.push({
          x: anchor.x + dx * ratio + (-dy / distance) * laneOffset,
          y: anchor.y + dy * ratio + (dx / distance) * laneOffset,
        });
        candidates.set(node.id, current);
      });
    }

    const preferred = new Map<string, { x: number; y: number }>();
    for (const [id, candidate] of candidates) {
      if (targetPosition.has(id)) {
        preferred.set(id, targetPosition.get(id)!);
        continue;
      }
      const sum = candidate.proposed.reduce(
        (total, point) => ({ x: total.x + point.x, y: total.y + point.y }),
        { x: 0, y: 0 },
      );
      preferred.set(id, {
        x: sum.x / candidate.proposed.length,
        y: sum.y / candidate.proposed.length,
      });
    }
    return preferred;
  }, [graphEdges, highlightedPaths, perspectiveId, selectedTargets]);

  const openInfo = useCallback((person: Person) => {
    setInfoPerson(person);
  }, []);
  const onNodeDragStart = useCallback((event: DragEvent<HTMLElement>, personId: string) => {
    event.dataTransfer.setData(CONNECTIONS_PERSON_DRAG_TYPE, personId);
    event.dataTransfer.setData("text/plain", personId);
    event.dataTransfer.effectAllowed = "copyMove";
  }, []);

  const flowNodes = useMemo(() => {
    const nodes: Node[] = visibleNodeDtos.map((dto) => {
      const isFrom = dto.id === perspectiveId;
      const isTo = targetIds.has(dto.id);
      const isPath = availableNodeIds.has(dto.id);
      const isPathIntermediate = isPath && !isFrom && !isTo;
      const className = [
        selectedTargets.length && !isPath && !isFrom && !isTo ? "rf-dim" : "",
        isFrom ? "rf-node-from" : "",
        isTo ? "rf-node-to" : "",
        isPathIntermediate ? "rf-path-intermediate" : "",
      ].filter(Boolean).join(" ");
      const person = personOfNode(dto.id);
      return {
        id: dto.id,
        type: "person",
        position: { x: 0, y: 0 },
        // Explicit dimensions keep React Flow's controlled-node measurement
        // stable while an asynchronous route overlay updates its classes.
        // Without them, unchanged context cards can briefly be treated as
        // unmeasured and rendered with visibility:hidden.
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
        className: className || undefined,
        data: {
          id: dto.id,
          name: dto.name,
          subtitle: dto.relation_label_en ?? undefined,
          subtitleUr: dto.relation_label_ur ?? undefined,
          isPerspective: isFrom,
          isVirtual: dto.is_virtual ?? false,
          isFrom,
          isTo,
          isPathIntermediate,
          region: connectionRegion(dto, visibleEdgeDtos, perspectiveId, isPathIntermediate, isTo),
          preferredPosition: routePlacementById.get(dto.id),
          forcePreferredPosition: routePlacementById.has(dto.id),
          onInfo: person ? () => openInfo(person) : undefined,
          onDragStart: onNodeDragStart,
        },
      };
    });
    const positioned = layoutConnectionGraph(nodes, perspectiveId ?? undefined, positionStoreRef.current);
    for (const node of positioned) positionStoreRef.current.set(node.id, node.position);
    return positioned;
  }, [availableNodeIds, onNodeDragStart, openInfo, perspectiveId, personOfNode, routePlacementById, selectedTargets.length, targetIds, visibleEdgeDtos, visibleNodeDtos]);

  const flowEdges = useMemo(() => {
    const positions = new Map(flowNodes.map((node) => [node.id, node.position]));
    return buildFlowEdges(
      visibleEdgeDtos,
      highlightedPaths,
      highlightedEdges,
      availableEdges,
      positions,
      selectedTargets.length > 0,
    );
  }, [availableEdges, flowNodes, highlightedEdges, highlightedPaths, selectedTargets.length, visibleEdgeDtos]);

  useEffect(() => {
    if (!perspectiveId || graph.loading || !visibleNodeDtos.length || fittedPerspectiveRef.current === perspectiveId) return;
    fittedPerspectiveRef.current = perspectiveId;
    const frame = window.setTimeout(() => {
      void fitView({ padding: 0.07, duration: 320, maxZoom: 1.05 });
    }, 60);
    return () => window.clearTimeout(frame);
  }, [fitView, graph.loading, perspectiveId, visibleNodeDtos.length]);

  const immediateConnections = useMemo<ImmediateConnection[]>(() => {
    if (!perspectiveId) return [];
    const directIds = new Set(
      graphEdges
        .filter((edge) => edge.source === perspectiveId || edge.target === perspectiveId)
        .map((edge) => edge.source === perspectiveId ? edge.target : edge.source),
    );
    return graphNodes
      .filter((node) => directIds.has(node.id))
      .flatMap((node): ImmediateConnection[] => {
        const person = personOfNode(node.id);
        return person ? [{ person, label: node.relation_label_en ?? undefined }] : [];
      })
      .sort((first, second) => first.person.name.localeCompare(second.person.name));
  }, [graphEdges, graphNodes, perspectiveId, personOfNode]);

  const handleHighlightedPathsChange = useCallback((personId: string, paths: RelationshipPath[]) => {
    setHighlightedPathsByTarget((current) => {
      const existing = current[personId] ?? [];
      if (existing.length === paths.length && existing.every((path, index) => path.id === paths[index]?.id)) return current;
      if (!paths.length) {
        if (!(personId in current)) return current;
        const next = { ...current };
        delete next[personId];
        return next;
      }
      return { ...current, [personId]: paths };
    });
  }, []);

  const handleAvailablePathsChange = useCallback((personId: string, paths: RelationshipPath[]) => {
    setAvailablePathsByTarget((current) => {
      const existing = current[personId] ?? [];
      if (existing.length === paths.length && existing.every((path, index) => path.id === paths[index]?.id)) return current;
      if (!paths.length) {
        if (!(personId in current)) return current;
        const next = { ...current };
        delete next[personId];
        return next;
      }
      return { ...current, [personId]: paths };
    });
  }, []);

  const exitPathMode = useCallback(() => {
    setHighlightedPathsByTarget({});
    setClearPathsVersion((value) => value + 1);
  }, []);

  useEffect(() => {
    const syncFullscreenState = () => {
      const active = document.fullscreenElement === graphAreaRef.current;
      setNativeFullscreen(active);
      if (!document.fullscreenElement) setImmersive(false);
    };
    document.addEventListener("fullscreenchange", syncFullscreenState);
    return () => document.removeEventListener("fullscreenchange", syncFullscreenState);
  }, []);

  const exitImmersive = useCallback(async () => {
    if (document.fullscreenElement === graphAreaRef.current) await document.exitFullscreen();
    setNativeFullscreen(false);
    setImmersive(false);
  }, []);
  const toggleImmersive = useCallback(async () => {
    if (immersive || document.fullscreenElement === graphAreaRef.current) {
      await exitImmersive();
      return;
    }
    try {
      await graphAreaRef.current?.requestFullscreen?.();
      setNativeFullscreen(Boolean(graphAreaRef.current));
    } catch {
      // The canvas fallback remains useful in desktop webviews that deny fullscreen.
    }
    setImmersive(true);
  }, [exitImmersive, immersive]);

  const focusSearch = useCallback(() => {
    setSearchOpen(true);
    window.requestAnimationFrame(() => searchInputRef.current?.focus());
  }, []);
  const onEscape = useCallback(() => {
    if (infoPerson) { setInfoPerson(null); return; }
    if (immersive || nativeFullscreen) { void exitImmersive(); return; }
    if (searchOpen || searchSelection) {
      setSearchOpen(false);
      setSearchSelection(null);
      return;
    }
    if (highlightedPaths.length) { exitPathMode(); return; }
    if (comparePicker) setComparePicker(false);
    if (compareTarget) setCompareTarget(null);
  }, [comparePicker, compareTarget, exitImmersive, exitPathMode, highlightedPaths.length, immersive, infoPerson, nativeFullscreen, searchOpen, searchSelection]);

  useKeyboardNavigation({
    onSearch: focusSearch,
    onViewFromSelected: () => { if (selected) setFrom(selected); },
    onCompare: () => { if (selected) setComparePicker(true); },
    onShowPrimaryPath: () => { if (selected) addTo(selected); },
    onReturnHome: () => { void returnToDefault(); },
    onExitPath: exitPathMode,
    onEscape,
  });

  const perspectiveName = perspectivePerson?.name ?? perspectiveId ?? "";
  const contextIslandStyle = useMemo(() => {
    const snapshot = immediateContext?.perspectiveId === perspectiveId
      ? immediateContext
      : { nodes: graphNodes, edges: graphEdges };
    const counts = { maternal: 0, paternal: 0, external: 0 };
    for (const node of snapshot.nodes) {
      if (node.id === perspectiveId) continue;
      const region = connectionRegion(node, snapshot.edges, perspectiveId, false, false);
      if (region === "maternal" || region === "paternal" || region === "external") counts[region] += 1;
    }
    const sizeFor = (count: number, baseWidth: number, baseHeight: number) => ({
      width: count ? `${Math.min(baseWidth + count * 38, baseWidth + 148)}px` : "0px",
      height: count ? `${Math.min(baseHeight + Math.ceil(count / 2) * 42, baseHeight + 112)}px` : "0px",
    });
    const maternal = sizeFor(counts.maternal, 166, 112);
    const paternal = sizeFor(counts.paternal, 166, 112);
    const external = sizeFor(counts.external, 238, 82);
    return {
      "--maternal-island-width": maternal.width,
      "--maternal-island-height": maternal.height,
      "--paternal-island-width": paternal.width,
      "--paternal-island-height": paternal.height,
      "--external-island-width": external.width,
      "--external-island-height": external.height,
    } as CSSProperties;
  }, [graphEdges, graphNodes, immediateContext, perspectiveId]);
  const pathContent = perspectiveId ? (
    <div className="relationship-target-stack">
      {selectedTargets.map((person) => (
        <RelationshipTargetCard
          key={person.id}
          person={person}
          perspectiveId={perspectiveId}
          perspectiveName={perspectiveName}
          active={selected?.id === person.id}
          refreshVersion={0}
          clearPathsVersion={clearPathsVersion}
          onActivate={() => setSelected(person)}
          onRemove={() => removeTarget(person.id)}
          onOpenInfo={() => openInfo(person)}
          onHighlightedPathsChange={handleHighlightedPathsChange}
          onAvailablePathsChange={handleAvailablePathsChange}
        />
      ))}
    </div>
  ) : null;

  return (
    <div className="view relationships-view">
      <div className="relationships-head view-head sr-only">
        <h1>Connections <span>Relationship Explorer</span></h1>
        <p>Immediate connections from {perspectiveName}’s perspective.</p>
      </div>
      <ErrorNote error={graph.error || relationshipError} />
      <div className="relationships-diagram-layout">
        <div
          ref={graphAreaRef}
          className={`relationships-graph-area ${immersive ? "is-immersive" : ""}`}
          data-immersive={immersive ? "true" : "false"}
        >
          <div className="relationship-side-context" aria-hidden="true" style={contextIslandStyle}>
            <div className="relationship-context-region maternal">Maternal context</div>
            <div className="relationship-context-region paternal">Paternal context</div>
            <div className="relationship-context-region external">External connections</div>
          </div>
          <div className="relationship-graph-stage has-inspector">
            <ReactFlow
              nodes={flowNodes}
              edges={flowEdges}
              nodeTypes={nodeTypes}
              minZoom={0.42}
              maxZoom={2.5}
              nodesDraggable={false}
              nodesConnectable={false}
              elementsSelectable={false}
              onlyRenderVisibleElements={false}
              deleteKeyCode={null}
              zoomOnDoubleClick={false}
              onMove={(_, viewport) => setZoomPercent(Math.round(viewport.zoom * 100))}
              onNodeClick={(_, node) => {
                const person = personOfNode(node.id);
                if (person) selectPerson(person);
              }}
              onNodeDoubleClick={(_, node) => {
                const person = personOfNode(node.id);
                if (person) setFrom(person);
              }}
              onPaneClick={() => { setSearchOpen(false); setSearchSelection(null); }}
              proOptions={{ hideAttribution: true }}
            >
              <Background variant={BackgroundVariant.Dots} gap={24} size={1.3} color="var(--graph-dot)" bgColor="transparent" />
            </ReactFlow>
          </div>

          <div className="connections-search-dock">
            {!searchOpen ? (
              <Button kind="ghost" className="connections-search-trigger" onClick={focusSearch} ariaLabel="Open Connections search" title="Search people"><Icon name="search" size={20} /></Button>
            ) : (
              <div className="relationships-search-wrap glass-panel" role="dialog" aria-label="Connections search">
                <div className="connections-search-input-row">
                  <span className="connections-search-icon" aria-hidden="true"><Icon name="search" size={18} /></span>
                  <PersonSearch
                    people={people}
                    onSelect={(person) => {
                      selectPerson(person);
                      setSearchSelection(person);
                      window.requestAnimationFrame(() => setSearchOpen(true));
                    }}
                    placeholder="Search people… (Ctrl+K)"
                    inputRef={(node) => { searchInputRef.current = node; }}
                    onOpenChange={setSearchOpen}
                  />
                  <Button kind="ghost" className="icon-button connections-search-close" onClick={() => { setSearchOpen(false); setSearchSelection(null); searchInputRef.current?.blur(); }} ariaLabel="Close Connections search" title="Close search"><Icon name="close" /></Button>
                </div>
                {searchSelection && (
                  <div className="connections-search-actions" aria-label={`Actions for ${searchSelection.name}`}>
                    <Avatar person={searchSelection} size={27} />
                    <strong>{searchSelection.name}</strong>
                    <Button kind="ghost" onClick={() => { setFrom(searchSelection); setSearchOpen(false); setSearchSelection(null); }}>Set as FROM</Button>
                    <Button kind="primary" onClick={() => { addTo(searchSelection); setSearchOpen(false); setSearchSelection(null); }}>Add to TO</Button>
                  </div>
                )}
              </div>
            )}
          </div>

          {highlightedPaths.length > 0 && (
            <div className="graph-focus-badge">
              {highlightedPaths.length} route{highlightedPaths.length === 1 ? "" : "s"} focused · Esc clears
            </div>
          )}

          <RelationshipBuilder
            fromPerson={perspectivePerson}
            targets={selectedTargets}
            selectedPerson={selected}
            immediateConnections={immediateConnections}
            pathContent={pathContent}
            showReturnToPerspective={Boolean(defaultId && perspectiveId && defaultId !== perspectiveId)}
            onReturnToPerspective={() => { void returnToDefault(); }}
            onSetFrom={setFrom}
            onAddTo={addTo}
            onRemoveTo={removeTarget}
            onSelect={selectPerson}
            onInfo={openInfo}
            onClearTargets={clearTargets}
            onDropPerson={handleDropPerson}
          />

          {infoPerson && (
            <PersonInfoDrawer
              person={infoPerson}
              perspectiveId={perspectiveId}
              perspectiveName={perspectiveName}
              onClose={() => setInfoPerson(null)}
              onOpenJournal={setJournalFor}
              onNavigateToProfile={onNavigateToProfile}
              onNavigateToFamily={onNavigateToFamily}
            />
          )}

          <GraphDock
            personName={perspectiveName}
            zoomPercent={zoomPercent}
            immersive={immersive}
            onZoomOut={() => void zoomOut({ duration: 220 })}
            onZoomIn={() => void zoomIn({ duration: 220 })}
            onFit={() => void fitView({ padding: 0.07, duration: 320, maxZoom: 1.05 })}
            onToggleFullscreen={() => void toggleImmersive()}
          />
        </div>
      </div>

      {comparePicker && selected && (
        <Modal title={`Compare ${selected.name} with…`} onClose={() => setComparePicker(false)}>
          <div className="people-pick-list">
            {people.filter((person) => person.id !== selected.id).map((person) => (
              <button type="button" key={person.id} onClick={() => { setCompareTarget(person); setComparePicker(false); }}>
                <Avatar person={person} size={24} /><span>{person.name}</span>
              </button>
            ))}
          </div>
        </Modal>
      )}
      {compareTarget && selected && <CompareModal a={selected.id} b={compareTarget.id} onClose={() => setCompareTarget(null)} onViewFrom={(personId) => { const person = personOfNode(personId); if (person) setFrom(person); }} />}
      {journalFor && <JournalModal person={journalFor} onClose={() => setJournalFor(null)} />}
    </div>
  );
}

export function RelationshipsView(props: NavigationProps) {
  return <ReactFlowProvider><RelationshipsContent {...props} /></ReactFlowProvider>;
}
