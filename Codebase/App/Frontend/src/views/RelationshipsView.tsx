import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
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
  Modal,
  PersonSearch,
} from "../components/ui";
import { usePerspective } from "../state";
import type { Person } from "../types";
import { relationshipsApi } from "../features/relationships/api";
import { ExpandControls } from "../features/relationships/components/ExpandControls";
import { GraphLegend } from "../features/relationships/components/GraphLegend";
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
        stroke: focusPath && !isPath ? "#c3c9d4" : visual.stroke,
        strokeWidth: isPath ? 3 : visual.strokeWidth,
        strokeDasharray: visual.strokeDasharray,
        opacity: focusPath && !isPath ? 0.28 : 1,
      },
      className: focusPath && isPath ? "rf-edge-path" : undefined,
      label: focusPath && isPath ? pathRoleMap.get(pair) : undefined,
      labelStyle: { fontSize: 11, fill: "#40536f", fontWeight: 600 },
      labelBgStyle: { fill: "#ffffff", fillOpacity: 0.92 },
      labelBgPadding: [6, 3] as [number, number],
    };
  });
}

function RelationshipsContent({ initialTargetId }: { initialTargetId?: string | null }) {
  const { perspectiveId, perspectivePerson, setPerspective, returnToDefault } =
    usePerspective();
  const graph = useRelationshipGraph();
  const { fitView } = useReactFlow();
  const [people, setPeople] = useState<Person[]>([]);
  const [groups, setGroups] = useState<any[]>([]);
  const [selected, setSelected] = useState<Person | null>(null);
  const [relationshipResult, setRelationshipResult] = useState<{
    primary: RelationshipEntry[];
    additional: RelationshipEntry[];
  } | null>(null);
  const [relationshipError, setRelationshipError] = useState<unknown>(null);
  const [focus, setFocus] = useState<{
    entry: RelationshipEntry;
    paths: RelationshipPath[];
    pathIndex: number;
  } | null>(null);
  const [comparePicker, setComparePicker] = useState(false);
  const [compareTarget, setCompareTarget] = useState<Person | null>(null);
  const [journalFor, setJournalFor] = useState<Person | null>(null);
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const expandedCountRef = useRef(0);

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
    setSelected(null);
    setFocus(null);
    setRelationshipResult(null);
    expandedCountRef.current = 0;
    void graph.reset(perspectiveId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [perspectiveId]);

  useEffect(() => {
    void loadRelationships();
  }, [loadRelationships]);

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
      setFocus(null);
      graph.ensureVisible({
        id: person.id,
        name: person.name,
        is_perspective: person.id === perspectiveId,
      });
    },
    [graph, perspectiveId],
  );

  useEffect(() => {
    if (initialTargetId && people.length > 0) {
      const match = people.find((p) => p.id === initialTargetId);
      if (match) {
        selectPerson(match);
      }
    }
  }, [initialTargetId, people, selectPerson]);

  const showWhy = useCallback(
    async (entry: RelationshipEntry) => {
      if (!perspectiveId || !selected) return;
      graph.exitPath();
      try {
        const response = await relationshipsApi.paths(
          perspectiveId,
          selected.id,
        );
        const needle = entry.label_en.trim().toLowerCase();
        const matching = response.paths.filter(
          (path) => path.label_en.trim().toLowerCase() === needle,
        );
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
    window.setTimeout(() => fitView({ padding: 0.2, duration: 350 }), 40);
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
        () => fitView({ padding: 0.18, duration: 350, maxZoom: 1 }),
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
      const centerId = selected?.id ?? perspectiveId;
      if (centerId && perspectiveId) {
        void graph.toggleExpansion(centerId, perspectiveId, filter);
      }
    },
    [graph, perspectiveId, selected],
  );

  const activeFilters = useMemo(() => {
    const centerId = selected?.id ?? perspectiveId ?? "";
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
  }, [graph.expansions, perspectiveId, selected]);

  const focusSearch = useCallback(() => {
    searchInputRef.current?.focus();
  }, []);

  const showPrimaryPath = useCallback(() => {
    const primary = relationshipResult?.primary[0];
    if (primary) void showWhy(primary);
  }, [relationshipResult, showWhy]);

  const onEscape = useCallback(() => {
    if (focus) {
      exitPathMode();
      return;
    }
    if (comparePicker) setComparePicker(false);
    if (compareTarget) setCompareTarget(null);
  }, [comparePicker, compareTarget, exitPathMode, focus]);

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

  return (
    <div className="view relationships-view">
      <div className="view-head relationships-head">
        <div>
          <h1>Relationships</h1>
          <p className="muted">
            Diagram-first navigation from <strong>{perspectiveName}</strong>’s perspective.
          </p>
        </div>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          {selected && (
            <Button
              kind="primary"
              onClick={() => setShowAddRel(true)}
            >
              + Add Relationship
            </Button>
          )}
          <div className="relationships-search-wrap">
            <PersonSearch
              people={people}
              onSelect={(person) => selectPerson(person)}
              placeholder="Search people… (Ctrl+K)"
              inputRef={(node) => {
                searchInputRef.current = node;
              }}
            />
          </div>
        </div>
      </div>
      <ErrorNote error={graph.error || relationshipError} />

      <div className="relationships-diagram-layout">
        <div className="relationships-graph-area">
          <ReactFlow
            nodes={flowNodes}
            edges={flowEdges}
            nodeTypes={nodeTypes}
            minZoom={0.1}
            maxZoom={2.5}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable={false}
            deleteKeyCode={null}
            zoomOnDoubleClick={false}
            onNodeClick={(_, node) => {
              const person = personOfNode(node.id);
              if (person) selectPerson(person);
            }}
            onNodeDoubleClick={(_, node) => {
              const person = personOfNode(node.id);
              if (person) void setPerspective(person.id);
            }}
            onPaneClick={() => setSelected(null)}
            proOptions={{ hideAttribution: true }}
          >
            <Background variant={BackgroundVariant.Dots} gap={22} size={1.4} />
            <Controls showInteractive={false} />
            <MiniMap
              pannable
              zoomable
              nodeColor={(node) => {
                const data = node.data as { isPerspective?: boolean };
                if (node.className?.includes("rf-dim")) return "#d6dae2";
                return data?.isPerspective ? "#31547f" : "#aebdd0";
              }}
            />
          </ReactFlow>
          {focus && activePath && (
            <div className="graph-focus-badge">
              Path focus: {focus.entry.label_en} · press Esc to exit
            </div>
          )}
        </div>

        <aside className="relationships-panel">
          {focus && activePath && selected ? (
            <PathFocusPanel
              entry={focus.entry}
              path={activePath}
              perspectiveName={perspectiveName}
              target={selected}
              totalForLabel={focus.paths.length}
              onSelectPath={selectFocusedPath}
              onExit={exitPathMode}
            />
          ) : selected ? (
            <div className="selected-person-panel">
              <div className="side-profile-row">
                <Avatar person={selected} size={42} />
                <div>
                  <strong>{selected.name}</strong>
                  {selected.aliases.length > 0 && (
                    <div className="muted tiny">
                      Alias: {selected.aliases.join(", ")}
                    </div>
                  )}
                </div>
              </div>

              {/* Node Context Actions Toolbar */}
              <div className="row-actions" style={{ marginBottom: 12 }}>
                <Button kind="primary" onClick={() => setShowAddRel(true)}>
                  + Add Relationship
                </Button>
                <Button
                  kind="ghost"
                  onClick={() => {
                    setPersonModalTarget(selected);
                    setPersonModalMode("edit");
                  }}
                >
                  Edit Person
                </Button>
                <Button
                  kind="danger"
                  onClick={() => {
                    setPersonModalTarget(selected);
                    setPersonModalMode("delete");
                  }}
                >
                  Delete
                </Button>
              </div>

              <div className="rel-section-title">
                Relationship to {perspectiveName}
              </div>

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
                  {relationshipResult.primary.length === 0 &&
                    relationshipResult.additional.length === 0 && (
                      <div className="empty-inline">
                        No recorded relationship from this perspective.
                      </div>
                    )}
                </>
              ) : (
                <div className="muted small">Calculating…</div>
              )}

              <div className="row-actions panel-actions">
                <Button
                  kind="primary"
                  onClick={() => void setPerspective(selected.id)}
                >
                  View from this person
                </Button>
                <Button onClick={() => setComparePicker(true)}>Compare</Button>
                <Button onClick={() => setJournalFor(selected)}>Journal</Button>
              </div>
            </div>
          ) : (
            <div className="empty-state panel-empty">
              <strong>Selected Person</strong>
              <p>
                Search above or click a node to see every relationship from{" "}
                {perspectiveName}’s perspective.
              </p>
            </div>
          )}
        </aside>
      </div>

      <div className="relationships-footer">
        <ExpandControls
          personName={centerPerson?.name ?? "…"}
          active={activeFilters}
          onToggle={toggleExpansionForCenter}
        />
        <GraphLegend />
        <div className="keyboard-hints muted tiny">
          Ctrl+K search · V view from selected · C compare · P show primary · H
          owner perspective · Esc exit path
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
          key={`${entry.relationship_type}-${index}`}
          style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6 }}
        >
          <div className="panel-rel-label" style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span>{entry.label_en}</span>
            <span className={`badge-fact ${entry.derived ? "badge-derived" : "badge-explicit"}`}>
              {entry.derived ? "derived" : "explicit"}
            </span>
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
      ))}
    </div>
  );
}

export function RelationshipsView({ initialTargetId }: { initialTargetId?: string | null }) {
  return (
    <ReactFlowProvider>
      <RelationshipsContent initialTargetId={initialTargetId} />
    </ReactFlowProvider>
  );
}
