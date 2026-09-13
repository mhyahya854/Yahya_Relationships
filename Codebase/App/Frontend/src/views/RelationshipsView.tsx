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
import { relationshipsApi } from "../features/relationships/api";
import { GraphDock } from "../features/relationships/components/GraphDock";
import { PathFocusPanel } from "../features/relationships/components/PathFocusPanel";
import { PersonNode } from "../features/relationships/components/PersonNode";
import { edgeVisual } from "../features/relationships/graph/edgeStyles";
import { layoutGraph } from "../features/relationships/graph/layout";
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

function buildRoleMap(path: RelationshipPath): Map<string, string> {
  const map = new Map<string, string>();
  for (const edge of path.edges) {
    map.set(pathPairKey(edge.from, edge.to), edge.role ?? "");
  }
  return map;
}

function buildFlowEdges(
  edgeDtos: GraphEdgeDto[],
  focusPath: RelationshipPath | null,
  pathRoleMap: Map<string, string>,
): Edge[] {
  return edgeDtos.map((dto) => {
    const visual = edgeVisual(dto);
    const pair = pathPairKey(dto.source, dto.target);
    const isPath = focusPath ? pathRoleMap.has(pair) : false;
    return {
      id: dto.id,
      source: dto.source,
      target: dto.target,
      type: "default",
      style: {
        stroke: focusPath && !isPath ? "var(--disabled-fg)" : visual.stroke,
        strokeWidth: isPath ? 3 : visual.strokeWidth,
        strokeDasharray: visual.strokeDasharray,
        opacity: focusPath && !isPath ? 0.28 : 1,
      },
      className: focusPath && isPath ? "rf-edge-path" : undefined,
      label: focusPath && isPath ? pathRoleMap.get(pair) : undefined,
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
  const { fitView, zoomIn, zoomOut } = useReactFlow();
  const [people, setPeople] = useState<Person[]>([]);
  const [peopleLoaded, setPeopleLoaded] = useState(false);
  const [groups, setGroups] = useState<any[]>([]);
  const [selected, setSelected] = useState<Person | null>(null);
  const [relationshipResult, setRelationshipResult] = useState<{
    primary: RelationshipEntry[];
    additional: RelationshipEntry[];
  } | null>(null);
  const [relationshipError, setRelationshipError] = useState<unknown>(null);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [focus, setFocus] = useState<{
    entry: RelationshipEntry;
    paths: RelationshipPath[];
    pathIndex: number;
  } | null>(null);
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

  const loadRelationships = useCallback(async () => {
    if (!perspectiveId || !selected) return;
    try {
      const payload = await api.relationships.get(perspectiveId, selected.id);
      setRelationshipResult({
        primary: payload.primary,
        additional: payload.additional,
      });
      setRelationshipError(null);
    } catch (err: unknown) {
      setRelationshipError(err);
    }
  }, [perspectiveId, selected]);

  useEffect(() => {
    if (!perspectiveId) return;
    setFocus(null);
    setRelationshipResult(null);
    expandedCountRef.current = 0;
    void graph.reset(perspectiveId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [perspectiveId]);

  useEffect(() => {
    void loadRelationships();
  }, [loadRelationships]);

  useEffect(() => {
    setEvidenceOpen(Boolean(relationshipResult?.additional.length));
  }, [relationshipResult, selected?.id]);

  const handleSavedMutation = async (desc: string) => {
    setUndoNotice(desc);
    await loadPeopleAndGroups();
    if (perspectiveId) {
      void graph.reset(perspectiveId);
    }
    if (selected) {
      void loadRelationships();
    }
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
        if (selected) {
          void loadRelationships();
        }
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
      setSelected(person);
      onTargetChange?.(person.id);
      setRelationshipError(null);
      setFocus(null);
      graph.exitPath();
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

  const showWhy = useCallback(
    async (entry: RelationshipEntry) => {
      if (!perspectiveId || !selected) return;
      graph.exitPath();
      try {
        const response = await relationshipsApi.paths(
          perspectiveId,
          selected.id,
        );
        let matching: RelationshipPath[] = [];
        if (entry.path_ids && entry.path_ids.length > 0) {
          const pathIdSet = new Set(entry.path_ids);
          matching = response.paths.filter((p) => pathIdSet.has(p.id));
        }
        if (!matching.length && (entry.semantic_id || entry.relationship_type)) {
          const semId = entry.semantic_id || entry.relationship_type;
          matching = response.paths.filter(
            (p) => (p.semantic_id || p.relationship_type) === semId,
          );
        }
        const paths = matching.length ? matching : response.paths;
        if (!paths.length) {
          setRelationshipError(
            new Error(
              "No supported relationship path was found within max depth.",
            ),
          );
          return;
        }
        setRelationshipError(null);
        setFocus({ entry, paths, pathIndex: 0 });
        graph.focusPath(paths[0]);
      } catch (err) {
        setRelationshipError(err);
      }
    },
    [graph, perspectiveId, selected],
  );

  const selectFocusedPath = useCallback(
    (index: number) => {
      if (!focus) return;
      const path = focus.paths[index];
      if (!path) return;
      graph.exitPath();
      graph.focusPath(path);
      setFocus({ ...focus, pathIndex: index });
    },
    [focus, graph],
  );

  const exitPathMode = useCallback(() => {
    if (!focus) return;
    setFocus(null);
    graph.exitPath();
    window.setTimeout(() => fitView({ padding: 0.1, duration: 350, maxZoom: 1 }), 40);
  }, [focus, graph, fitView]);

  const activePath = focus ? focus.paths[focus.pathIndex] : null;
  const pathNodeIds = useMemo(() => {
    const ids = new Set<string>();
    if (activePath) {
      activePath.nodes.forEach((node) => ids.add(node.id));
    }
    return ids;
  }, [activePath]);
  const pathRoleMap = useMemo(
    () => (activePath ? buildRoleMap(activePath) : new Map<string, string>()),
    [activePath],
  );

  const flowEdges: Edge[] = useMemo(
    () => buildFlowEdges(visibleEdgeDtos, activePath, pathRoleMap),
    [visibleEdgeDtos, activePath, pathRoleMap],
  );

  const flowNodes: Node[] = useMemo(() => {
    const nodes = visibleNodeDtos.map((dto) => {
      const isPath = pathNodeIds.has(dto.id);
      const className = focus
        ? isPath
          ? "rf-path-node"
          : "rf-dim"
        : dto.id === selected?.id
          ? "rf-node-selected"
          : "";
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
    return layoutGraph(nodes, flowEdges);
  }, [
    visibleNodeDtos,
    focus,
    pathNodeIds,
    perspectiveId,
    selected,
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
    if (!activePath) return;
    const ids = activePath.nodes.map((node) => node.id);
    const frame = window.setTimeout(() => {
      fitView({
        nodes: ids.map((id) => ({ id })),
        padding: 0.3,
        duration: 600,
      });
    }, 120);
    return () => window.clearTimeout(frame);
  }, [activePath, fitView]);

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
    const primary = relationshipResult?.primary[0];
    if (primary) void showWhy(primary);
  }, [relationshipResult, showWhy]);

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
    if (focus) {
      exitPathMode();
      return;
    }
    if (comparePicker) setComparePicker(false);
    if (compareTarget) setCompareTarget(null);
  }, [comparePicker, compareTarget, exitImmersive, exitPathMode, focus, immersive, nativeFullscreen]);

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

  const centerPerson = selected ?? perspectivePerson ?? null;
  const perspectiveName = perspectivePerson?.name ?? perspectiveId ?? "";
  const primaryRelationship = relationshipResult?.primary[0] ?? null;

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
          <div className={`relationship-graph-stage ${selected ? "has-inspector" : ""}`}>
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
                setSelected(null);
                onTargetChange?.(null);
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
          {focus && activePath && (
            <div className="graph-focus-badge">
              Path focus: {focus.entry.label_en} · press Esc to exit
            </div>
          )}
          {selected ? (
        <aside className="relationships-panel glass-panel">
          {focus && activePath && selected ? (
            <PathFocusPanel
              entry={focus.entry}
              path={activePath}
              perspectiveName={perspectiveName}
              target={selected}
              totalForLabel={focus.paths.length}
              activeIndex={focus.pathIndex}
              onSelectPath={selectFocusedPath}
              onExit={exitPathMode}
            />
          ) : selected ? (
            <div className="selected-person-panel">
              <div className="inspector-profile-row">
                <Avatar person={selected} size={60} />
                <div className="inspector-profile-copy">
                  <strong>{selected.name}</strong>
                  <div className="inspector-relationship-line">
                    {primaryRelationship?.label_en ?? "Connection"}
                    {primaryRelationship?.label_ur && (
                      <span dir="rtl" lang="ur"> · {primaryRelationship.label_ur}</span>
                    )}
                  </div>
                </div>
                <Button kind="ghost" className="icon-button inspector-close" onClick={() => {
                  setSelected(null);
                  onTargetChange?.(null);
                }} ariaLabel="Close selected person" title="Close selected person"><Icon name="close" /></Button>
              </div>

              <div className="inspector-primary-actions">
                {onNavigateToProfile && (
                  <Button onClick={() => onNavigateToProfile(selected.id)}><Icon name="profile" /> <span>View Profile</span><span className="inspector-chevron">›</span></Button>
                )}
                <Button onClick={() => setJournalFor(selected)}><Icon name="journal" /> <span>Journal</span><span className="inspector-chevron">›</span></Button>
                <Button onClick={() => void setPerspective(selected.id)}><Icon name="path" /> <span>View from this person</span><span className="inspector-chevron">›</span></Button>
              </div>

              <div className="inspector-metadata">
                <div className="inspector-meta-row">
                  <Icon name="profile" />
                  <div><span>Full name</span><strong>{selected.name}</strong></div>
                </div>
                <div className="inspector-meta-row">
                  <Icon name="family" />
                  <div><span>Relationship to {perspectiveName}</span><strong>{primaryRelationship?.label_en ?? "Not recorded"}</strong></div>
                </div>
                <div className="inspector-meta-row">
                  <Icon name="journal" />
                  <div><span>Perspectives available</span><strong>View their family and connections</strong></div>
                </div>
              </div>

              <details
                className="inspector-disclosure inspector-evidence"
                open={evidenceOpen}
                onToggle={(event) => setEvidenceOpen(event.currentTarget.open)}
              >
                <summary><Icon name="path" /> Relationship evidence</summary>
                <div className="inspector-disclosure-body">
                  {relationshipResult ? (
                    <>
                      <EntryGroup
                        title="Primary"
                        entries={relationshipResult.primary}
                        onShowWhy={(entry) => void showWhy(entry)}
                        onEditEntry={(entry) => setEditingEntry(entry)}
                      />
                      {relationshipResult.additional.length > 0 && (
                        <EntryGroup
                          title="Additional paths"
                          entries={relationshipResult.additional}
                          onShowWhy={(entry) => void showWhy(entry)}
                          onEditEntry={(entry) => setEditingEntry(entry)}
                        />
                      )}
                      {relationshipResult.primary.length === 0 && relationshipResult.additional.length === 0 && (
                        <div className="empty-inline">No recorded relationship from this perspective.</div>
                      )}
                    </>
                  ) : (
                    <div className="muted small">Calculating…</div>
                  )}
                </div>
              </details>

              <details className="inspector-disclosure inspector-manage">
                <summary><Icon name="more" /> More actions</summary>
                <div className="inspector-disclosure-body inspector-manage-grid">
                  <Button kind="primary" onClick={() => setShowAddRel(true)}><Icon name="add" /> Add Relationship</Button>
                  {onNavigateToFamily && (
                    <Button onClick={() => onNavigateToFamily(selected.id)}><Icon name="family" /> View Family Tree<span className="sr-only"> View Family</span></Button>
                  )}
                  <Button onClick={() => setComparePicker(true)}><Icon name="compare" /> Compare</Button>
                  <Button onClick={() => { setPersonModalTarget(selected); setPersonModalMode("edit"); }}><Icon name="edit" /> Edit Person</Button>
                  <Button kind="danger" onClick={() => { setPersonModalTarget(selected); setPersonModalMode("delete"); }}>Delete Person</Button>
                </div>
              </details>
            </div>
          ) : null}
        </aside>
          ) : null}

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

function EntryGroup({
  title,
  entries,
  onShowWhy,
  onEditEntry,
}: {
  title: string;
  entries: RelationshipEntry[];
  onShowWhy: (entry: RelationshipEntry) => void;
  onEditEntry: (entry: RelationshipEntry) => void;
}) {
  return (
    <div className="panel-rel-group">
      <div className="rel-section-title">{title}</div>
      {entries.map((entry, index) => (
        <div
          className="panel-rel-row"
          key={`${entry.relationship_type}-${entry.semantic_id || ""}-${index}`}
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 4,
            padding: "8px 0",
            borderBottom: "1px solid var(--border-subtle)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6 }}>
            <div className="panel-rel-label" style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 6 }}>
              <span style={{ fontWeight: 600 }}>{entry.label_en}</span>
              <span
                className={`badge-fact ${entry.derived ? "badge-derived" : "badge-explicit"}`}
                title={entry.derived ? "Derived from stored family facts" : "Directly stored factual data"}
              >
                {entry.derived ? "derived" : "stored fact"}
              </span>
              {entry.side && entry.side !== "unspecified" && (
                <span className="badge-fact badge-side">
                  {entry.side}
                </span>
              )}
              {entry.kind && entry.kind !== "direct" && (
                <span className="badge-fact badge-kind">
                  {entry.kind}
                </span>
              )}
            </div>
            <div style={{ display: "flex", gap: 4 }}>
              <Button kind="ghost" onClick={() => onEditEntry(entry)}>
                {entry.derived ? "Source" : "Edit"}
              </Button>
              <Button kind="ghost" onClick={() => onShowWhy(entry)}>
                Why
              </Button>
            </div>
          </div>
          {entry.label_ur && (
            <div className="relation-ur" dir="rtl" lang="ur" style={{ fontSize: 13, color: "var(--text-secondary)" }}>
              {entry.label_ur}
            </div>
          )}
        </div>
      ))}
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
