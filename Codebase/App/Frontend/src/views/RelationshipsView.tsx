import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from "react";
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
import { layoutConnectionGraph } from "../features/relationships/graph/layout";
import { useKeyboardNavigation } from "../features/relationships/hooks/useKeyboardNavigation";
import { useRelationshipGraph } from "../features/relationships/hooks/useRelationshipGraph";
import type { GraphEdgeDto, GraphNodeDto, RelationshipPath } from "../features/relationships/types";

const nodeTypes = { person: PersonNode };

function pathPairKey(first: string, second: string): string {
  return [first, second].sort().join("::");
}

function pathEdgeDetails(paths: RelationshipPath[]): Map<string, Set<string>> {
  const details = new Map<string, Set<string>>();
  for (const path of paths) {
    for (const edge of path.edges) {
      const key = pathPairKey(edge.from, edge.to);
      const labels = details.get(key) ?? new Set<string>();
      if (edge.role) labels.add(edge.role);
      details.set(key, labels);
    }
  }
  return details;
}

function buildFlowEdges(
  edgeDtos: GraphEdgeDto[],
  highlightedPaths: RelationshipPath[],
  highlightedEdges: Map<string, Set<string>>,
): Edge[] {
  const hasHighlights = highlightedPaths.length > 0;
  return edgeDtos.map((dto) => {
    const visual = edgeVisual(dto);
    const labels = highlightedEdges.get(pathPairKey(dto.source, dto.target));
    const isPath = Boolean(labels);
    return {
      id: dto.id,
      source: dto.source,
      target: dto.target,
      type: "smoothstep",
      style: {
        stroke: isPath ? "var(--accent-primary)" : visual.stroke,
        strokeWidth: isPath ? 3 : visual.strokeWidth,
        strokeDasharray: visual.strokeDasharray,
        opacity: hasHighlights && !isPath ? 0.28 : 1,
      },
      className: [visual.className, isPath ? "rf-edge-path" : "", hasHighlights && !isPath ? "rf-edge-dim" : ""].filter(Boolean).join(" "),
      label: labels?.size ? [...labels].join(" · ") : undefined,
      labelStyle: { fontSize: 11, fill: "var(--text-secondary)", fontWeight: 600 },
      labelBgStyle: { fill: "var(--surface-elevated)", fillOpacity: 0.94 },
      labelBgPadding: [6, 3] as [number, number],
    };
  });
}

function connectionRegion(
  node: GraphNodeDto,
  edges: GraphEdgeDto[],
  fromId: string | null,
  isPathIntermediate: boolean,
): "origin" | "maternal" | "paternal" | "external" | "family" | "path" {
  if (node.id === fromId) return "origin";
  if (isPathIntermediate) return "path";
  const label = (node.relation_label_en ?? "").toLowerCase();
  if (/maternal|mother|mami|mama/.test(label)) return "maternal";
  if (/paternal|father|chachi|chacha/.test(label)) return "paternal";
  if (edges.some((edge) => (edge.source === node.id || edge.target === node.id) && edge.domain === "general")) {
    return "external";
  }
  return "family";
}

interface NavigationProps {
  initialTargetId?: string | null;
  onTargetChange?: (personId: string | null) => void;
  onTargetUnavailable?: (personId: string) => void;
  onNavigateToProfile?: (personId: string) => void;
  onNavigateToFamily?: (personId: string) => void;
}

function RelationshipsContent({
  initialTargetId,
  onTargetChange,
  onTargetUnavailable,
}: NavigationProps) {
  const { perspectiveId, perspectivePerson, defaultId, setPerspective, returnToDefault } = usePerspective();
  const graph = useRelationshipGraph();
  const { fitView, zoomIn, zoomOut } = useReactFlow();
  const [people, setPeople] = useState<Person[]>([]);
  const [peopleLoaded, setPeopleLoaded] = useState(false);
  const [selected, setSelected] = useState<Person | null>(null);
  const [selectedTargets, setSelectedTargets] = useState<Person[]>([]);
  const [highlightedPathsByTarget, setHighlightedPathsByTarget] = useState<Record<string, RelationshipPath[]>>({});
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
    setSelectedTargets((current) => current.filter((person) => person.id !== perspectiveId));
    setSelected((current) => current?.id === perspectiveId ? null : current);
    positionStoreRef.current.clear();
    fittedPerspectiveRef.current = null;
    void graph.reset(perspectiveId);
    // The perspective is FROM; it is the only operation that resets the base graph.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [perspectiveId]);

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
    setSelectedTargets((current) => current.some((target) => target.id === person.id)
      ? current
      : [...current, person]);
    onTargetChange?.(person.id);
  }, [onTargetChange, perspectiveId, selectPerson]);

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
  }, [onTargetChange]);

  const clearTargets = useCallback(() => {
    setSelectedTargets([]);
    setHighlightedPathsByTarget({});
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

  useEffect(() => {
    if (highlightedPaths.length) graph.focusPaths(highlightedPaths);
    else graph.exitPath();
  }, [graph.exitPath, graph.focusPaths, highlightedPaths]);

  const visibleNodeDtos = useMemo(() => {
    const nodes = new Map<string, GraphNodeDto>();
    for (const node of [...graph.nodes, ...graph.overlayNodes]) nodes.set(node.id, node);
    return [...nodes.values()];
  }, [graph.nodes, graph.overlayNodes]);
  const visibleEdgeDtos = useMemo(() => {
    const edges = new Map<string, GraphEdgeDto>();
    for (const edge of [...graph.edges, ...graph.overlayEdges]) edges.set(edge.id, edge);
    return [...edges.values()];
  }, [graph.edges, graph.overlayEdges]);
  const highlightedNodeIds = useMemo(
    () => new Set(highlightedPaths.flatMap((path) => path.nodes.map((node) => node.id))),
    [highlightedPaths],
  );
  const highlightedEdges = useMemo(() => pathEdgeDetails(highlightedPaths), [highlightedPaths]);
  const flowEdges = useMemo(
    () => buildFlowEdges(visibleEdgeDtos, highlightedPaths, highlightedEdges),
    [highlightedEdges, highlightedPaths, visibleEdgeDtos],
  );
  const targetIds = useMemo(() => new Set(selectedTargets.map((person) => person.id)), [selectedTargets]);

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
      const isPath = highlightedNodeIds.has(dto.id);
      const isPathIntermediate = isPath && !isFrom && !isTo;
      const className = [
        highlightedPaths.length && !isPath && !isFrom && !isTo ? "rf-dim" : "",
        isFrom ? "rf-node-from" : "",
        isTo ? "rf-node-to" : "",
        isPathIntermediate ? "rf-path-intermediate" : "",
      ].filter(Boolean).join(" ");
      const person = personOfNode(dto.id);
      return {
        id: dto.id,
        type: "person",
        position: { x: 0, y: 0 },
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
          region: connectionRegion(dto, visibleEdgeDtos, perspectiveId, isPathIntermediate),
          onInfo: person ? () => openInfo(person) : undefined,
          onDragStart: onNodeDragStart,
        },
      };
    });
    const positioned = layoutConnectionGraph(nodes, perspectiveId ?? undefined, positionStoreRef.current);
    for (const node of positioned) positionStoreRef.current.set(node.id, node.position);
    return positioned;
  }, [highlightedNodeIds, highlightedPaths.length, onNodeDragStart, openInfo, perspectiveId, personOfNode, targetIds, visibleEdgeDtos, visibleNodeDtos]);

  useEffect(() => {
    if (!perspectiveId || graph.loading || !visibleNodeDtos.length || fittedPerspectiveRef.current === perspectiveId) return;
    fittedPerspectiveRef.current = perspectiveId;
    const frame = window.setTimeout(() => {
      void fitView({ padding: 0.15, duration: 320, maxZoom: 1 });
    }, 60);
    return () => window.clearTimeout(frame);
  }, [fitView, graph.loading, perspectiveId, visibleNodeDtos.length]);

  const immediateConnections = useMemo<ImmediateConnection[]>(() => {
    if (!perspectiveId) return [];
    const directIds = new Set(
      graph.edges
        .filter((edge) => edge.source === perspectiveId || edge.target === perspectiveId)
        .map((edge) => edge.source === perspectiveId ? edge.target : edge.source),
    );
    return graph.nodes
      .filter((node) => directIds.has(node.id))
      .flatMap((node): ImmediateConnection[] => {
        const person = personOfNode(node.id);
        return person ? [{ person, label: node.relation_label_en ?? undefined }] : [];
      })
      .sort((first, second) => first.person.name.localeCompare(second.person.name));
  }, [graph.edges, graph.nodes, perspectiveId, personOfNode]);

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
    if (highlightedPaths.length) { exitPathMode(); return; }
    if (comparePicker) setComparePicker(false);
    if (compareTarget) setCompareTarget(null);
  }, [comparePicker, compareTarget, exitImmersive, exitPathMode, highlightedPaths.length, immersive, infoPerson, nativeFullscreen]);

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
          <div className="relationship-side-context" aria-hidden="true">
            <div className="relationship-context-region maternal">Maternal context</div>
            <div className="relationship-context-region paternal">Paternal context</div>
            <div className="relationship-context-region external">External connections</div>
          </div>
          <div className="relationship-graph-stage has-inspector">
            <ReactFlow
              nodes={flowNodes}
              edges={flowEdges}
              nodeTypes={nodeTypes}
              minZoom={0.3}
              maxZoom={2.5}
              nodesDraggable={false}
              nodesConnectable={false}
              elementsSelectable={false}
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
              onPaneClick={() => { setSearchOpen(false); }}
              proOptions={{ hideAttribution: true }}
            >
              <Background variant={BackgroundVariant.Dots} gap={24} size={1.3} color="var(--graph-dot)" bgColor="transparent" />
            </ReactFlow>
          </div>

          <div className="connections-search-dock">
            <div className={`relationships-search-wrap glass-panel ${searchOpen ? "open" : "collapsed"}`} onFocusCapture={() => setSearchOpen(true)}>
              <span className="connections-search-icon" aria-hidden="true"><Icon name="search" size={20} /></span>
              <PersonSearch
                people={people}
                onSelect={(person) => {
                  selectPerson(person);
                  setSearchSelection(person);
                  setSearchOpen(false);
                }}
                placeholder="Search people… (Ctrl+K)"
                inputRef={(node) => { searchInputRef.current = node; }}
                onOpenChange={setSearchOpen}
              />
              {searchOpen && <Button kind="ghost" className="icon-button connections-search-close" onClick={() => { setSearchOpen(false); searchInputRef.current?.blur(); }} ariaLabel="Close Connections search" title="Close search"><Icon name="close" /></Button>}
            </div>
            {searchSelection && (
              <div className="connections-search-actions glass-panel" aria-label={`Actions for ${searchSelection.name}`}>
                <Avatar person={searchSelection} size={27} />
                <strong>{searchSelection.name}</strong>
                <Button kind="ghost" onClick={() => setFrom(searchSelection)}>Set as FROM</Button>
                <Button kind="primary" onClick={() => addTo(searchSelection)}>Add to TO</Button>
                <Button kind="ghost" className="icon-button" onClick={() => setSearchSelection(null)} ariaLabel="Close search result actions" title="Close"><Icon name="close" /></Button>
              </div>
            )}
          </div>

          {highlightedPaths.length > 0 && (
            <div className="graph-focus-badge">
              {highlightedPaths.length} selected route{highlightedPaths.length === 1 ? "" : "s"} · surrounding context remains visible · Esc clears route selection
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
            />
          )}

          <GraphDock
            personName={perspectiveName}
            zoomPercent={zoomPercent}
            immersive={immersive}
            onZoomOut={() => void zoomOut({ duration: 220 })}
            onZoomIn={() => void zoomIn({ duration: 220 })}
            onFit={() => void fitView({ padding: 0.14, duration: 320, maxZoom: 1 })}
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
