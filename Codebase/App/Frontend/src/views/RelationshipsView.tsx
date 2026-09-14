import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import {
  Avatar,
  Button,
  ErrorNote,
  Icon,
  Modal,
  PersonSearch,
} from "../components/ui";
import { usePerspective } from "../state";
import type { Person } from "../types";
import { GraphDock } from "../features/relationships/components/GraphDock";
import { PersonNode } from "../features/relationships/components/PersonNode";
import { RelationshipTargetCard } from "../features/relationships/components/RelationshipTargetCard";
import { edgeVisual } from "../features/relationships/graph/edgeStyles";
import { layoutGraph, NODE_HEIGHT, NODE_WIDTH } from "../features/relationships/graph/layout";
import { useKeyboardNavigation } from "../features/relationships/hooks/useKeyboardNavigation";
import { useRelationshipGraph } from "../features/relationships/hooks/useRelationshipGraph";
import type {
  ExpansionFilter,
  GraphEdgeDto,
  GraphNodeDto,
  RelationshipEntry,
  RelationshipPath,
} from "../features/relationships/types";
import { AddRelationshipDialog } from "../features/relationships/components/AddRelationshipDialog";
import { EditRelationshipDialog } from "../features/relationships/components/EditRelationshipDialog";
import { PersonEditorModal } from "../features/people/components/PersonEditorModal";
import { UndoBar } from "../features/mutations/components/UndoBar";

const nodeTypes = { person: PersonNode };

function pathPairKey(a: string, b: string): string {
  return [a, b].sort().join("::");
}

type PathHighlight = {
  roles: Set<string>;
  maternal: boolean;
  paternal: boolean;
  general: boolean;
};

function buildPathHighlights(paths: RelationshipPath[]): Map<string, PathHighlight> {
  const map = new Map<string, PathHighlight>();
  for (const path of paths) {
    for (const edge of path.edges) {
      const pair = pathPairKey(edge.from, edge.to);
      const highlight = map.get(pair) ?? {
        roles: new Set<string>(),
        maternal: false,
        paternal: false,
        general: false,
      };
      if (edge.role) highlight.roles.add(edge.role);
      if (path.domain === "general") highlight.general = true;
      if (path.domain === "family" && path.side === "maternal") highlight.maternal = true;
      if (path.domain === "family" && path.side === "paternal") highlight.paternal = true;
      map.set(pair, highlight);
    }
  }
  return map;
}

function buildFlowEdges(
  edgeDtos: GraphEdgeDto[],
  highlightedPaths: RelationshipPath[],
  pathHighlights: Map<string, PathHighlight>,
): Edge[] {
  const hasHighlights = highlightedPaths.length > 0;
  return edgeDtos.map((dto) => {
    const visual = edgeVisual(dto);
    const pair = pathPairKey(dto.source, dto.target);
    const highlight = pathHighlights.get(pair);
    const isPath = Boolean(highlight);
    const isOverlap = Boolean(highlight?.maternal && highlight?.paternal);
    const className = [
      isPath ? "rf-edge-path" : "",
      highlight?.maternal ? "rf-edge-maternal" : "",
      highlight?.paternal ? "rf-edge-paternal" : "",
      highlight?.general ? "rf-edge-general" : "",
      isOverlap ? "rf-edge-overlap" : "",
    ].filter(Boolean).join(" ");
    const highlightedStroke = isOverlap
      ? "var(--family-line)"
      : highlight?.maternal
        ? "var(--maternal)"
        : highlight?.paternal
          ? "var(--paternal)"
          : visual.stroke;
    return {
      id: dto.id,
      source: dto.source,
      target: dto.target,
      type: "smoothstep",
      style: {
        stroke: isPath ? highlightedStroke : visual.stroke,
        strokeWidth: isPath ? 3 : visual.strokeWidth,
        strokeDasharray: visual.strokeDasharray,
        opacity: hasHighlights && !isPath ? 0.34 : 1,
      },
      className: className || undefined,
      label: highlight?.roles.size ? [...highlight.roles].join(" · ") : undefined,
      labelStyle: { fontSize: 11, fill: "var(--text-secondary)", fontWeight: 600 },
      labelBgStyle: { fill: "var(--surface-elevated)", fillOpacity: 0.94 },
      labelBgPadding: [6, 3] as [number, number],
    };
  });
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
  onNavigateToProfile,
  onNavigateToFamily,
}: NavigationProps) {
  const { perspectiveId, perspectivePerson, setPerspective, returnToDefault } =
    usePerspective();
  const graph = useRelationshipGraph();
  const { fitBounds, fitView, zoomIn, zoomOut } = useReactFlow();
  const [people, setPeople] = useState<Person[]>([]);
  const [peopleLoaded, setPeopleLoaded] = useState(false);
  const [groups, setGroups] = useState<any[]>([]);
  const [selected, setSelected] = useState<Person | null>(null);
  const [selectedTargets, setSelectedTargets] = useState<Person[]>([]);
  const [relationshipError, setRelationshipError] = useState<unknown>(null);
  const [highlightedPathsByTarget, setHighlightedPathsByTarget] = useState<Record<string, RelationshipPath[]>>({});
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [revealPathsVersion, setRevealPathsVersion] = useState(0);
  const [clearPathsVersion, setClearPathsVersion] = useState(0);
  const [comparePicker, setComparePicker] = useState(false);
  const [compareTarget, setCompareTarget] = useState<Person | null>(null);
  const [journalFor, setJournalFor] = useState<Person | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const graphAreaRef = useRef<HTMLDivElement | null>(null);
  const expandedCountRef = useRef(0);
  const appliedInitialTargetRef = useRef<string | null>(null);
  const [immersive, setImmersive] = useState(false);
  const [nativeFullscreen, setNativeFullscreen] = useState(false);
  const [zoomPercent, setZoomPercent] = useState(100);

  // Editor Modals State
  const [showAddRel, setShowAddRel] = useState(false);
  const [editingEntry, setEditingEntry] = useState<RelationshipEntry | null>(null);
  const [personModalMode, setPersonModalMode] = useState<"add" | "edit" | "delete" | null>(null);
  const [personModalTarget, setPersonModalTarget] = useState<Person | null>(null);
  const [undoNotice, setUndoNotice] = useState<string | null>(null);

  const loadPeopleAndGroups = useCallback(async () => {
    try {
      const pRes = await api.people.list();
      setPeople(pRes.people);
      const gRes = await api.groups.list();
      setGroups(gRes.groups);
    } catch {
      // ignore
    } finally {
      setPeopleLoaded(true);
    }
  }, []);

  useEffect(() => {
    void loadPeopleAndGroups();
  }, [loadPeopleAndGroups]);

  useEffect(() => {
    if (!perspectiveId) return;
    setHighlightedPathsByTarget({});
    setSelectedTargets((current) => current.filter((person) => person.id !== perspectiveId));
    setSelected((current) => current?.id === perspectiveId ? null : current);
    expandedCountRef.current = 0;
    void graph.reset(perspectiveId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [perspectiveId]);

  const handleSavedMutation = async (desc: string) => {
    setUndoNotice(desc);
    await loadPeopleAndGroups();
    if (perspectiveId) {
      void graph.reset(perspectiveId);
    }
    setRefreshVersion((value) => value + 1);
  };

  const handleUndo = async () => {
    try {
      const res = await api.mutations.undo();
      if (res.ok) {
        setUndoNotice(null);
        await loadPeopleAndGroups();
        if (perspectiveId) {
          void graph.reset(perspectiveId);
        }
        setRefreshVersion((value) => value + 1);
      }
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Undo failed");
    }
  };

  const visibleNodeDtos: GraphNodeDto[] = useMemo(
    () => [...graph.nodes, ...graph.overlayNodes],
    [graph.nodes, graph.overlayNodes],
  );
  const visibleEdgeDtos: GraphEdgeDto[] = useMemo(
    () => [...graph.edges, ...graph.overlayEdges],
    [graph.edges, graph.overlayEdges],
  );

  const personOfNode = useCallback(
    (nodeId: string): Person | undefined =>
      people.find((person) => person.id === nodeId),
    [people],
  );

  const selectPerson = useCallback(
    (person: Person) => {
      if (person.id === perspectiveId) return;
      setSelected(person);
      setSelectedTargets((current) => current.some((target) => target.id === person.id)
        ? current
        : [...current, person]);
      onTargetChange?.(person.id);
      setRelationshipError(null);
      graph.ensureVisible({
        id: person.id,
        name: person.name,
        is_perspective: person.id === perspectiveId,
      });
    },
    [graph, onTargetChange, perspectiveId],
  );

  useEffect(() => {
    if (!peopleLoaded) return;
    if (!initialTargetId) {
      appliedInitialTargetRef.current = null;
      return;
    }
    if (appliedInitialTargetRef.current === initialTargetId) return;
    appliedInitialTargetRef.current = initialTargetId;
    if (initialTargetId) {
      const match = people.find((p) => p.id === initialTargetId);
      if (match && selected?.id !== match.id) {
        selectPerson(match);
      } else if (!match) {
        setSelected(null);
        setRelationshipError(new Error("That relationship target is no longer available in this Data Root."));
        onTargetUnavailable?.(initialTargetId);
      }
    }
  }, [initialTargetId, onTargetUnavailable, people, peopleLoaded, selectPerson, selected?.id]);

  const highlightedPaths = useMemo(
    () => Object.values(highlightedPathsByTarget).flat(),
    [highlightedPathsByTarget],
  );

  useEffect(() => {
    if (highlightedPaths.length) graph.focusPaths(highlightedPaths);
    else graph.exitPath();
  }, [graph.exitPath, graph.focusPaths, highlightedPaths]);

  const pathNodeHighlights = useMemo(() => {
    const map = new Map<string, { maternal: boolean; paternal: boolean; general: boolean }>();
    for (const path of highlightedPaths) {
      for (const node of path.nodes) {
        const value = map.get(node.id) ?? { maternal: false, paternal: false, general: false };
        if (path.domain === "general") value.general = true;
        if (path.domain === "family" && path.side === "maternal") value.maternal = true;
        if (path.domain === "family" && path.side === "paternal") value.paternal = true;
        map.set(node.id, value);
      }
    }
    return map;
  }, [highlightedPaths]);

  const pathHighlights = useMemo(
    () => buildPathHighlights(highlightedPaths),
    [highlightedPaths],
  );

  const flowEdges: Edge[] = useMemo(
    () => buildFlowEdges(visibleEdgeDtos, highlightedPaths, pathHighlights),
    [visibleEdgeDtos, highlightedPaths, pathHighlights],
  );

  const flowNodes: Node[] = useMemo(() => {
    const nodes = visibleNodeDtos.map((dto) => {
      const pathTone = pathNodeHighlights.get(dto.id);
      const isPath = Boolean(pathTone);
      const isTarget = selectedTargets.some((person) => person.id === dto.id);
      const className = [
        highlightedPaths.length && !isPath ? "rf-dim" : "",
        isPath ? "rf-path-node" : "",
        pathTone?.maternal ? "rf-path-maternal" : "",
        pathTone?.paternal ? "rf-path-paternal" : "",
        pathTone?.general ? "rf-path-general" : "",
        pathTone?.maternal && pathTone?.paternal ? "rf-path-overlap" : "",
        isTarget ? "rf-node-selected" : "",
        dto.id === selected?.id ? "rf-node-active-target" : "",
      ].filter(Boolean).join(" ");
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
          isPerspective: dto.id === perspectiveId,
          isVirtual: dto.is_virtual ?? false,
        },
      };
    });
    return layoutGraph(nodes, flowEdges, "TB", perspectiveId ?? undefined);
  }, [
    visibleNodeDtos,
    highlightedPaths.length,
    pathNodeHighlights,
    perspectiveId,
    selected,
    selectedTargets,
    flowEdges,
  ]);

  useEffect(() => {
    const count = visibleNodeDtos.length;
    if (count && count !== expandedCountRef.current) {
      expandedCountRef.current = count;
      const frame = window.setTimeout(
        () => fitView({ padding: 0.1, duration: 350, maxZoom: 1 }),
        60,
      );
      return () => window.clearTimeout(frame);
    }
  }, [visibleNodeDtos.length, fitView]);

  useEffect(() => {
    if (!highlightedPaths.length) return;
    const frame = window.setTimeout(() => {
      const highlightedNodeIds = new Set(
        highlightedPaths.flatMap((path) => path.nodes.map((node) => node.id)),
      );
      if (perspectiveId) highlightedNodeIds.add(perspectiveId);
      for (const [targetId, paths] of Object.entries(highlightedPathsByTarget)) {
        if (paths.length) highlightedNodeIds.add(targetId);
      }
      const pathNodes = flowNodes.filter((node) => highlightedNodeIds.has(node.id));
      if (!pathNodes.length) return;
      const minX = Math.min(...pathNodes.map((node) => node.position.x));
      const minY = Math.min(...pathNodes.map((node) => node.position.y));
      const maxX = Math.max(...pathNodes.map((node) => node.position.x + NODE_WIDTH));
      const maxY = Math.max(...pathNodes.map((node) => node.position.y + NODE_HEIGHT));
      void fitBounds(
        { x: minX, y: minY, width: Math.max(NODE_WIDTH, maxX - minX), height: Math.max(NODE_HEIGHT, maxY - minY) },
        { padding: 0.18, duration: 220 },
      );
    }, 160);
    return () => window.clearTimeout(frame);
  }, [fitBounds, flowNodes, highlightedPaths, highlightedPathsByTarget, perspectiveId]);

  // The inspector changes the React Flow viewport width. Refit only after its
  // width transition has settled; fitting against the old width can leave the
  // meaningful graph cropped behind the panel or entirely outside the stage.
  useEffect(() => {
    const frame = window.setTimeout(() => {
      fitView({ padding: 0.12, duration: 0, maxZoom: 1 });
    }, 360);
    return () => window.clearTimeout(frame);
  }, [fitView, selectedTargets.length]);

  const toggleExpansionForCenter = useCallback(
    (filter: ExpansionFilter) => {
      const centerId = perspectiveId;
      if (centerId && perspectiveId) {
        void graph.toggleExpansion(centerId, perspectiveId, filter);
      }
    },
    [graph, perspectiveId],
  );

  const activeFilters = useMemo(() => {
    const centerId = perspectiveId ?? "";
    const filters = new Set<ExpansionFilter>();
    const valid = ["parents", "children", "siblings", "spouses", "general"];
    for (const key of Object.keys(graph.expansions)) {
      const separator = key.indexOf(":");
      if (separator === -1) continue;
      const personId = key.slice(0, separator);
      const filter = key.slice(separator + 1);
      if (personId === centerId && valid.includes(filter)) {
        filters.add(filter as ExpansionFilter);
      }
    }
    return filters;
  }, [graph.expansions, perspectiveId]);

  const focusSearch = useCallback(() => {
    setSearchOpen(true);
    window.requestAnimationFrame(() => searchInputRef.current?.focus());
  }, []);

  const showPrimaryPath = useCallback(() => {
    if (selected) setRevealPathsVersion((value) => value + 1);
  }, [selected]);

  const exitPathMode = useCallback(() => {
    setHighlightedPathsByTarget({});
    setClearPathsVersion((value) => value + 1);
    graph.exitPath();
    window.setTimeout(() => fitView({ padding: 0.1, duration: 350, maxZoom: 1 }), 40);
  }, [graph, fitView]);

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
    if (document.fullscreenElement === graphAreaRef.current) {
      await document.exitFullscreen();
    }
    setNativeFullscreen(false);
    setImmersive(false);
    window.setTimeout(() => fitView({ padding: 0.1, duration: 350, maxZoom: 1 }), 60);
  }, [fitView]);

  const toggleImmersive = useCallback(async () => {
    if (immersive || document.fullscreenElement === graphAreaRef.current) {
      await exitImmersive();
      return;
    }
    const graphArea = graphAreaRef.current;
    if (!graphArea) return;
    try {
      if (graphArea.requestFullscreen) {
        await graphArea.requestFullscreen();
        setNativeFullscreen(true);
      }
    } catch {
      // Desktop webviews may deny the Fullscreen API. The fixed-position
      // immersive fallback preserves the same graph behavior and Escape exit.
    }
    setImmersive(true);
    window.setTimeout(() => fitView({ padding: 0.1, duration: 350, maxZoom: 1 }), 80);
  }, [exitImmersive, fitView, immersive]);

  const onEscape = useCallback(() => {
    if (immersive || nativeFullscreen) {
      void exitImmersive();
      return;
    }
    if (highlightedPaths.length) {
      exitPathMode();
      return;
    }
    if (comparePicker) setComparePicker(false);
    if (compareTarget) setCompareTarget(null);
  }, [comparePicker, compareTarget, exitImmersive, exitPathMode, highlightedPaths.length, immersive, nativeFullscreen]);

  useKeyboardNavigation({
    onSearch: focusSearch,
    onViewFromSelected: () => {
      if (selected) void setPerspective(selected.id);
    },
    onCompare: () => {
      if (selected) setComparePicker(true);
    },
    onShowPrimaryPath: showPrimaryPath,
    onReturnHome: () => void returnToDefault(),
    onExitPath: exitPathMode,
    onEscape,
  });

  const handleHighlightedPathsChange = useCallback((personId: string, paths: RelationshipPath[]) => {
    setHighlightedPathsByTarget((current) => {
      const existing = current[personId] ?? [];
      if (existing.length === paths.length && existing.every((path, index) => path.id === paths[index]?.id)) {
        return current;
      }
      if (!paths.length) {
        if (!(personId in current)) return current;
        const next = { ...current };
        delete next[personId];
        return next;
      }
      return { ...current, [personId]: paths };
    });
  }, []);

  const activateTarget = useCallback((person: Person) => {
    setSelected(person);
    onTargetChange?.(person.id);
  }, [onTargetChange]);

  const removeTarget = useCallback((personId: string) => {
    const nextTargets = selectedTargets.filter((person) => person.id !== personId);
    setSelectedTargets(nextTargets);
    if (selected?.id === personId) {
      const nextActive = nextTargets[0] ?? null;
      setSelected(nextActive);
      onTargetChange?.(nextActive?.id ?? null);
    }
    setHighlightedPathsByTarget((current) => {
      if (!(personId in current)) return current;
      const next = { ...current };
      delete next[personId];
      return next;
    });
  }, [onTargetChange, selected?.id, selectedTargets]);

  const centerPerson = perspectivePerson ?? null;
  const perspectiveName = perspectivePerson?.name ?? perspectiveId ?? "";

  return (
    <div className="view relationships-view">
      <div className="relationships-head view-head sr-only">
        <h1>Connections <span>Relationships</span></h1>
        <p>Connections from {perspectiveName}’s perspective.</p>
      </div>
      <ErrorNote error={graph.error || relationshipError} />

      <div className="relationships-diagram-layout">
        <div
          ref={graphAreaRef}
          className={`relationships-graph-area ${immersive ? "is-immersive" : ""}`}
          data-immersive={immersive ? "true" : "false"}
        >
          <div className={`relationship-graph-stage ${selectedTargets.length ? "has-inspector" : ""}`}>
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
                if (person) void setPerspective(person.id);
              }}
              onPaneClick={() => {
                setSearchOpen(false);
              }}
              proOptions={{ hideAttribution: true }}
            >
              <Background
                variant={BackgroundVariant.Dots}
                gap={22}
                size={1.4}
                color="var(--graph-dot)"
                bgColor="var(--graph-canvas)"
              />
            </ReactFlow>
          </div>
          <div className="connections-search-dock">
            <div
              className={`relationships-search-wrap glass-panel ${searchOpen ? "open" : "collapsed"}`}
              onFocusCapture={() => setSearchOpen(true)}
            >
              <span className="connections-search-icon" aria-hidden="true"><Icon name="search" size={20} /></span>
              <PersonSearch
                people={people}
                onSelect={(person) => {
                  selectPerson(person);
                  setSearchOpen(false);
                }}
                placeholder="Search people… (Ctrl+K)"
                inputRef={(node) => {
                  searchInputRef.current = node;
                }}
                onOpenChange={setSearchOpen}
              />
              {searchOpen && (
                <Button
                  kind="ghost"
                  className="icon-button connections-search-close"
                  onClick={() => {
                    setSearchOpen(false);
                    searchInputRef.current?.blur();
                  }}
                  ariaLabel="Close Connections search"
                  title="Close search"
                >
                  <Icon name="close" />
                </Button>
              )}
            </div>
          </div>
          {highlightedPaths.length > 0 && (
            <div className="graph-focus-badge">
              {highlightedPaths.length} highlighted path{highlightedPaths.length === 1 ? "" : "s"} across {Object.keys(highlightedPathsByTarget).filter((id) => highlightedPathsByTarget[id]?.length).length} target{Object.keys(highlightedPathsByTarget).filter((id) => highlightedPathsByTarget[id]?.length).length === 1 ? "" : "s"} · press Esc to clear
            </div>
          )}
          {selectedTargets.length > 0 && perspectiveId && (
            <aside className="relationships-panel relationship-explorer glass-panel" aria-label="Relationship Explorer">
              <div className="relationship-explorer-head">
                <div>
                  <strong>Relationship Explorer</strong>
                  <span>{selectedTargets.length} target{selectedTargets.length === 1 ? "" : "s"} relative to {perspectiveName}</span>
                </div>
                <Button
                  kind="ghost"
                  onClick={() => {
                    setSelectedTargets([]);
                    setSelected(null);
                    setHighlightedPathsByTarget({});
                    onTargetChange?.(null);
                  }}
                >
                  Clear all
                </Button>
              </div>
              <div className="relationship-target-stack">
                {selectedTargets.map((person) => (
                  <RelationshipTargetCard
                    key={person.id}
                    person={person}
                    perspectiveId={perspectiveId}
                    perspectiveName={perspectiveName}
                    active={selected?.id === person.id}
                    refreshVersion={refreshVersion}
                    revealPathsVersion={selected?.id === person.id ? revealPathsVersion : 0}
                    clearPathsVersion={clearPathsVersion}
                    onActivate={() => activateTarget(person)}
                    onRemove={() => removeTarget(person.id)}
                    onMakeCentral={() => void setPerspective(person.id)}
                    onHighlightedPathsChange={handleHighlightedPathsChange}
                    onNavigateToProfile={onNavigateToProfile}
                    onOpenJournal={setJournalFor}
                    onNavigateToFamily={onNavigateToFamily}
                    onAddRelationship={() => { activateTarget(person); setShowAddRel(true); }}
                    onEditRelationship={(entry) => { activateTarget(person); setEditingEntry(entry); }}
                    onCompare={() => { activateTarget(person); setComparePicker(true); }}
                    onEditPerson={() => { activateTarget(person); setPersonModalTarget(person); setPersonModalMode("edit"); }}
                    onDeletePerson={() => { activateTarget(person); setPersonModalTarget(person); setPersonModalMode("delete"); }}
                  />
                ))}
              </div>
            </aside>
          )}

          <GraphDock
            personName={centerPerson?.name ?? "…"}
            active={activeFilters}
            zoomPercent={zoomPercent}
            immersive={immersive}
            onToggle={toggleExpansionForCenter}
            onZoomOut={() => void zoomOut({ duration: 220 })}
            onZoomIn={() => void zoomIn({ duration: 220 })}
            onFit={() => void fitView({ padding: 0.1, duration: 350, maxZoom: 1 })}
            onToggleFullscreen={() => void toggleImmersive()}
          />
        </div>
      </div>

      {showAddRel && selected && (
        <AddRelationshipDialog
          sourcePerson={selected}
          peopleList={people}
          onClose={() => setShowAddRel(false)}
          onSaved={handleSavedMutation}
        />
      )}

      {editingEntry && selected && perspectivePerson && (
        <EditRelationshipDialog
          perspectivePerson={perspectivePerson}
          targetPerson={selected}
          entry={editingEntry}
          onClose={() => setEditingEntry(null)}
          onSaved={handleSavedMutation}
        />
      )}

      {personModalMode && (
        <PersonEditorModal
          mode={personModalMode}
          person={personModalTarget}
          groups={groups}
          onClose={() => {
            setPersonModalMode(null);
            setPersonModalTarget(null);
          }}
          onSaved={handleSavedMutation}
        />
      )}

      {comparePicker && selected && (
        <Modal
          title={`Compare ${selected.name} with…`}
          onClose={() => setComparePicker(false)}
        >
          <div className="people-pick-list">
            {people
              .filter((person) => person.id !== selected.id)
              .map((person) => (
                <button
                  type="button"
                  key={person.id}
                  onClick={() => {
                    setCompareTarget(person);
                    setComparePicker(false);
                  }}
                >
                  <Avatar person={person} size={24} />
                  <span>{person.name}</span>
                </button>
              ))}
          </div>
        </Modal>
      )}

      {compareTarget && selected && (
        <CompareModal
          a={selected.id}
          b={compareTarget.id}
          onClose={() => setCompareTarget(null)}
          onViewFrom={(personId) => void setPerspective(personId)}
        />
      )}

      {journalFor && (
        <JournalModal person={journalFor} onClose={() => setJournalFor(null)} />
      )}

      {undoNotice && (
        <UndoBar
          description={undoNotice}
          onUndo={handleUndo}
          onDismiss={() => setUndoNotice(null)}
        />
      )}
    </div>
  );
}

export function RelationshipsView(props: NavigationProps) {
  return (
    <ReactFlowProvider>
      <RelationshipsContent {...props} />
    </ReactFlowProvider>
  );
}
