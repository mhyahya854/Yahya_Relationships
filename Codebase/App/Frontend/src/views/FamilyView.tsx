import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Avatar, Button, ErrorNote, PersonSearch } from "../components/ui";
import { JournalModal, useRelationship } from "../components/PersonDetail";
import { usePerspective } from "../state";
import type { Group, Person, RelationshipEntry } from "../types";
import { AddRelationshipDialog } from "../features/relationships/components/AddRelationshipDialog";
import { EditRelationshipDialog } from "../features/relationships/components/EditRelationshipDialog";
import { PersonEditorModal } from "../features/people/components/PersonEditorModal";
import { UndoBar } from "../features/mutations/components/UndoBar";
import mermaid from "mermaid";

mermaid.initialize({
  startOnLoad: false,
  theme: "neutral",
  securityLevel: "strict",
  flowchart: {
    useMaxWidth: false,
    htmlLabels: true,
    curve: "basis",
    padding: 10,
  },
});

interface Props {
  onNavigateToProfile?: (personId: string) => void;
  onNavigateToRelationships?: (personId: string, fromPerspectiveId?: string) => void;
  focusPersonId?: string | null;
  onFocusPersonChange?: (personId: string) => void;
  selectedPersonId?: string | null;
  onSelectedPersonChange?: (personId: string | null) => void;
  initialFocusId?: string | null;
}

export function FamilyView({
  onNavigateToProfile,
  onNavigateToRelationships,
  focusPersonId: propFocusPersonId,
  onFocusPersonChange,
  selectedPersonId,
  onSelectedPersonChange,
  initialFocusId,
}: Props) {
  const { defaultId } = usePerspective();
  const [internalFocusId, setInternalFocusId] = useState<string>(
    propFocusPersonId || initialFocusId || defaultId || "",
  );
  const currentFocusId =
    propFocusPersonId !== undefined && propFocusPersonId !== null
      ? propFocusPersonId
      : internalFocusId;

  const handleFocusChange = (nextId: string) => {
    if (onFocusPersonChange) {
      onFocusPersonChange(nextId);
    } else {
      setInternalFocusId(nextId);
    }
  };

  const [defaultFocusId, setDefaultFocusId] = useState<string>(
    defaultId || "",
  );
  const [focusPerson, setFocusPerson] = useState<{
    id: string;
    name: string;
    gender?: string | null;
    birth_year?: number | null;
    branch?: string | null;
  } | null>(null);

  const [people, setPeople] = useState<Person[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [diagram, setDiagram] = useState<string | null>(null);
  const [legend, setLegend] = useState<
    Array<{ key: string; label: string; symbol: string; description: string }>
  >([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [selected, setSelected] = useState<Person | null>(null);
  const [zoom, setZoom] = useState(1);
  const [rendering, setRendering] = useState(false);
  const [showLegend, setShowLegend] = useState(true);

  const diagramRef = useRef<HTMLDivElement>(null);
  const renderCounter = useRef(0);
  const [journalFor, setJournalFor] = useState<Person | null>(null);

  // Editor Dialog States (preserved for seamless workflow)
  const [showAddFact, setShowAddFact] = useState(false);
  const [editingPerson, setEditingPerson] = useState<Person | null>(null);
  const [editingEntry, setEditingEntry] = useState<RelationshipEntry | null>(null);
  const [initialDeleteMode, setInitialDeleteMode] = useState<boolean>(false);
  const [relRefreshKey, setRelRefreshKey] = useState<number>(0);
  const [undoNotice, setUndoNotice] = useState<string | null>(null);

  const handleSelectPerson = (person: Person | null) => {
    setSelected(person);
    if (onSelectedPersonChange) {
      onSelectedPersonChange(person ? person.id : null);
    }
  };

  useEffect(() => {
    if (selectedPersonId && people.length > 0) {
      if (!selected || selected.id !== selectedPersonId) {
        const match = people.find((p) => p.id === selectedPersonId);
        if (match) {
          setSelected(match);
        } else {
          setSelected(null);
          onSelectedPersonChange?.(null);
        }
      }
    } else if (!selectedPersonId && selected) {
      setSelected(null);
    }
  }, [selectedPersonId, people]);

  const loadPeopleAndGroups = useCallback(async () => {
    try {
      const [peopleRes, groupsRes] = await Promise.all([
        api.people.list(),
        api.groups.list(),
      ]);
      setPeople(peopleRes.people);
      setGroups(groupsRes.groups);
    } catch {
      // Non-fatal if family.view supplies people
    }
  }, []);

  const loadFamilyData = useCallback(async (focusId: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.family.view(focusId);
      setDiagram(result.diagram);
      setDefaultFocusId(result.default_focus_id);
      if (result.focus) {
        setFocusPerson(result.focus);
      }
      if (result.people && result.people.length > 0) {
        setPeople(result.people as unknown as Person[]);
      }
      if (result.legend) {
        setLegend(result.legend);
      }
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadPeopleAndGroups();
  }, [loadPeopleAndGroups]);

  useEffect(() => {
    if (currentFocusId) {
      void loadFamilyData(currentFocusId);
    }
  }, [currentFocusId, loadFamilyData]);

  const handleSavedMutation = async (desc: string) => {
    setUndoNotice(desc);
    await loadPeopleAndGroups();
    if (currentFocusId) {
      await loadFamilyData(currentFocusId);
    }
    setRelRefreshKey((k) => k + 1);
  };

  const handleUndo = async () => {
    try {
      const res = await api.mutations.undo();
      if (res.ok) {
        setUndoNotice(null);
        await loadPeopleAndGroups();
        if (currentFocusId) {
          await loadFamilyData(currentFocusId);
        }
        setRelRefreshKey((k) => k + 1);
      }
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Undo failed");
    }
  };

  function highlightNode(container: HTMLElement, personId: string) {
    container.querySelectorAll(".family-highlight").forEach((node) => {
      node.classList.remove("family-highlight");
    });
    const node = container.querySelector<SVGElement>(
      `g.node[id*="-flowchart-p_${personId}-"], g.node[id*="p_${personId}"]`,
    );
    if (!node) return;
    node.classList.add("family-highlight");
    try {
      node.scrollIntoView({ block: "center", inline: "center", behavior: "smooth" });
    } catch {
      node.scrollIntoView();
    }
  }

  useEffect(() => {
    if (!diagram || !diagramRef.current) return;
    let cancelled = false;
    setRendering(true);
    renderCounter.current += 1;
    const container = diagramRef.current;
    const id = `pr-family-diagram-${renderCounter.current}`;

    mermaid
      .render(id, diagram)
      .then(({ svg }) => {
        if (cancelled) return;
        container.innerHTML = svg;
        container.querySelectorAll<SVGElement>('g.node[id*="-flowchart-p_"], g.node[id*="p_"]').forEach((node) => {
          const match = node.id.match(/-flowchart-p_([a-zA-Z0-9_]+)-\d+$/) || node.id.match(/p_([a-zA-Z0-9_]+)(?:-\d+)?$/);
          if (!match) return;
          const personId = match[1];
          node.classList.add("clickable-node");
          node.setAttribute("tabindex", "0");
          node.setAttribute("role", "button");
          node.setAttribute("aria-label", `Family member card: ${personId}`);

          const handleSelect = () => {
            const person = people.find((entry) => entry.id === personId);
            if (person) {
              handleSelectPerson(person);
              highlightNode(container, personId);
            }
          };

          node.addEventListener("click", handleSelect);
          node.addEventListener("keydown", (e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              handleSelect();
            }
          });

          node.addEventListener("dblclick", () => {
            const person = people.find((entry) => entry.id === personId);
            if (person) {
              handleFocusChange(person.id);
            }
          });
        });

        // Center current focus node after diagram render
        if (selected) {
          highlightNode(container, selected.id);
        } else if (currentFocusId) {
          highlightNode(container, currentFocusId);
        }
      })
      .catch((err: unknown) => setError(err))
      .finally(() => {
        if (!cancelled) setRendering(false);
      });

    return () => {
      cancelled = true;
    };
  }, [diagram, people, currentFocusId]);

  useEffect(() => {
    if (selected && diagramRef.current) {
      highlightNode(diagramRef.current, selected.id);
    }
  }, [selected]);

  const handleFit = () => {
    if (!diagramRef.current) return;
    const svg = diagramRef.current.querySelector("svg");
    const wrap = diagramRef.current.closest(".family-canvas-wrap");
    if (svg && wrap) {
      const wrapRect = wrap.getBoundingClientRect();
      const svgRect = svg.getBoundingClientRect();
      const scaleX = (wrapRect.width - 48) / (svg.clientWidth || svgRect.width);
      const scaleY = (wrapRect.height - 48) / (svg.clientHeight || svgRect.height);
      const newZoom = Math.min(1.0, Math.max(0.35, Math.min(scaleX, scaleY)));
      setZoom(+newZoom.toFixed(2));
    } else {
      setZoom(1);
    }
  };

  const handleCenterFocus = () => {
    setZoom(1);
    if (diagramRef.current && currentFocusId) {
      highlightNode(diagramRef.current, currentFocusId);
    }
  };

  const selectedRelationship = useRelationship(
    selected ? currentFocusId : null,
    selected ? selected.id : null,
    relRefreshKey,
  );

  const defaultFamilyFocusId = defaultFocusId || defaultId;
  const isDefaultFocus = Boolean(defaultFamilyFocusId) && currentFocusId === defaultFamilyFocusId;

  const focusPersonObj =
    people.find((p) => p.id === currentFocusId) ||
    (focusPerson
      ? ({
          ...focusPerson,
          aliases: [],
          groups: [],
          folder: null,
          note_en: null,
          note_ur: null,
          photo_path: null,
          marital_status: null,
        } as unknown as Person)
      : null);

  const primaryEntry = selectedRelationship.result?.primary?.[0] ?? null;
  const isPrimaryStored = Boolean(primaryEntry && primaryEntry.derived === false);

  return (
    <div className="view">
      <div className="view-head">
        <div>
          <h1>❖ Family Tree / خاندانی شجرہ</h1>
          <p className="muted">
            Genealogical structure and lineage derived by Python kinship engine — labels follow focus.
          </p>
        </div>
        <div className="family-controls">
          <Button
            onClick={() => setShowLegend((v) => !v)}
            title={showLegend ? "Hide Legend" : "Show Legend"}
          >
            {showLegend ? "Hide Legend" : "Show Legend"}
          </Button>
          <Button onClick={() => setZoom((v) => Math.min(2.5, +(v * 1.2).toFixed(2)))} title="Zoom in">
            + Zoom
          </Button>
          <Button onClick={() => setZoom((v) => Math.max(0.3, +(v / 1.2).toFixed(2)))} title="Zoom out">
            − Zoom
          </Button>
          <Button onClick={handleFit} title="Fit diagram to viewport">
            Fit
          </Button>
          <Button onClick={handleCenterFocus} title="Reset view and center on focus person">
            Center Focus
          </Button>
          <Button
            disabled={loading || rendering}
            onClick={() => {
              void loadPeopleAndGroups();
              void loadFamilyData(currentFocusId);
            }}
          >
            Reload
          </Button>
        </div>
      </div>

      {/* Focus Person Control Bar */}
      <div className="family-focus-bar">
        <span className="family-focus-label">Family Focus:</span>
        <div className="family-focus-current">
          {focusPerson && (
            <Avatar
              person={{
                id: focusPerson.id,
                name: focusPerson.name,
                gender: (focusPerson.gender as "male" | "female" | "unknown" | null) ?? null,
                birth_year: focusPerson.birth_year ?? null,
                marital_status: null,
                branch: focusPerson.branch ?? null,
                note_en: null,
                note_ur: null,
                photo_path: null,
                groups: [],
                aliases: [],
                folder: null,
              }}
              size={24}
            />
          )}
          <span>{focusPerson?.name ?? currentFocusId}</span>
        </div>

        <div className="family-focus-search-wrap">
          <PersonSearch
            people={people}
            onSelect={(person) => handleFocusChange(person.id)}
            placeholder="Search by name or alias…"
            ariaLabel="Search family focus by name or alias"
          />
        </div>

        {!isDefaultFocus && defaultFamilyFocusId && (
          <Button
            kind="ghost"
            onClick={() => handleFocusChange(defaultFamilyFocusId)}
            title="Return to default viewer focus"
          >
            Return to My Family View
          </Button>
        )}
      </div>

      {/* Diagram Legend */}
      {showLegend && (
        <div className="family-legend">
          <div className="legend-item">
            <span className="legend-swatch focus" />
            <span>
              <strong>Central Focus:</strong> {focusPerson?.name ?? "Selected Focus"} (Red border)
            </span>
          </div>
          <div className="legend-item">
            <span className="legend-swatch maternal" />
            <span>
              <strong>Maternal Branch:</strong> Pale pink clusters
            </span>
          </div>
          <div className="legend-item">
            <span className="legend-swatch paternal" />
            <span>
              <strong>Paternal Branch:</strong> Pale blue clusters
            </span>
          </div>
          <div className="legend-item">
            <span className="legend-swatch marriage" />
            <span>
              <strong>Marriage:</strong> Spouses joined horizontally
            </span>
          </div>
          <div className="legend-item">
            <span className="legend-swatch parent-child" />
            <span>
              <strong>Parent-Child:</strong> Junction downward to child
            </span>
          </div>
          <div className="legend-item">
            <span className="legend-swatch sibling" />
            <span>
              <strong>Sibling / Cross Link:</strong> Dotted link
            </span>
          </div>
        </div>
      )}

      <ErrorNote error={error} />
      {(loading || rendering) && <div className="state-box">Rendering family diagram…</div>}

      <div className="family-layout">
        <div className="family-canvas-wrap">
          <div
            className="family-canvas"
            style={{
              transform: `scale(${zoom})`,
              transformOrigin: "top left",
              width: zoom < 1 ? `${100 / zoom}%` : "100%",
            }}
          >
            <div className="family-diagram" ref={diagramRef} />
          </div>
        </div>

        {selected && (
          <aside className="family-side">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div className="side-profile-row">
                <Avatar person={selected} size={42} />
                <div>
                  <strong>{selected.name}</strong>
                  {selected.aliases && selected.aliases.length > 0 && (
                    <div className="muted tiny">{selected.aliases.join(" / ")}</div>
                  )}
                  {selected.groups?.[0] && (
                    <div className="muted tiny">{selected.groups[0].name}</div>
                  )}
                </div>
              </div>
              <Button kind="ghost" onClick={() => handleSelectPerson(null)} title="Close context panel">
                ✕
              </Button>
            </div>

            <div className="family-side-note">
              Click any card to inspect. Double-click to make that person the Family focus.
            </div>

            {/* Person Facts */}
            <div className="family-facts-list">
              {selected.birth_year && (
                <div className="family-fact-row">
                  <span className="family-fact-label">Born:</span>
                  <span>{selected.birth_year}</span>
                </div>
              )}
              {selected.gender && (
                <div className="family-fact-row">
                  <span className="family-fact-label">Gender:</span>
                  <span>
                    {selected.gender === "male"
                      ? "Male / مرد"
                      : selected.gender === "female"
                        ? "Female / عورت"
                        : selected.gender}
                  </span>
                </div>
              )}
              {selected.note_en && (
                <div className="family-fact-row">
                  <span className="family-fact-label">Note:</span>
                  <span>{selected.note_en}</span>
                </div>
              )}
            </div>

            {/* Relationship Context Section */}
            <h3>Relationship to {focusPerson?.name ?? "Focus"}</h3>
            {selectedRelationship.loading ? (
              <div className="muted">Calculating relationship…</div>
            ) : selectedRelationship.error ? (
              <ErrorNote error={selectedRelationship.error} />
            ) : selectedRelationship.result ? (
              <>
                <div className="rel-section-title">Primary Relationship</div>
                <RelationshipListDetailed
                  entries={selectedRelationship.result.primary}
                  onEditEntry={(entry) => {
                    setInitialDeleteMode(false);
                    setEditingEntry(entry);
                  }}
                  onDeleteEntry={(entry) => {
                    setInitialDeleteMode(true);
                    setEditingEntry(entry);
                  }}
                  onInspectProof={(entry) => {
                    setInitialDeleteMode(false);
                    setEditingEntry(entry);
                  }}
                />

                {/* Multi-path relationships */}
                {selectedRelationship.result.additional.length > 0 && (
                  <div className="rel-multipath-callout">
                    <div className="rel-multipath-title">
                      <span className="family-badge badge-multipath">
                        {selectedRelationship.result.additional.length + 1} family paths
                      </span>
                    </div>
                    <div className="muted tiny" style={{ marginBottom: 6 }}>
                      This relative is related through multiple genealogical branches:
                    </div>
                    <RelationshipListDetailed
                      entries={selectedRelationship.result.additional}
                      onEditEntry={(entry) => {
                        setInitialDeleteMode(false);
                        setEditingEntry(entry);
                      }}
                      onDeleteEntry={(entry) => {
                        setInitialDeleteMode(true);
                        setEditingEntry(entry);
                      }}
                      onInspectProof={(entry) => {
                        setInitialDeleteMode(false);
                        setEditingEntry(entry);
                      }}
                    />
                  </div>
                )}
              </>
            ) : null}

            {/* Actions */}
            <div className="row-actions family-side-actions">
              <Button
                kind="primary"
                onClick={() => handleFocusChange(selected.id)}
                title="Re-orient entire family tree around this person"
              >
                Make Family Focus
              </Button>
              {onNavigateToProfile && (
                <Button
                  onClick={() => onNavigateToProfile(selected.id)}
                  title="Open canonical Person Profile"
                >
                  View Profile
                </Button>
              )}
              {onNavigateToRelationships && (
                <Button
                  onClick={() => onNavigateToRelationships(selected.id, currentFocusId)}
                  title="Explore detailed proof paths in Relationships view"
                >
                  View in Relationships
                </Button>
              )}
              <Button onClick={() => setJournalFor(selected)}>Journal</Button>
            </div>

            {/* Fact Editor Actions */}
            <div className="row-actions" style={{ marginTop: 8, borderTop: "1px solid var(--line)", paddingTop: 8 }}>
              <Button onClick={() => setShowAddFact(true)}>+ Add Family Fact</Button>
              <Button
                disabled={!isPrimaryStored}
                onClick={() => {
                  if (primaryEntry) {
                    setInitialDeleteMode(false);
                    setEditingEntry(primaryEntry);
                  }
                }}
                title={
                  isPrimaryStored
                    ? "Edit stored family fact"
                    : "Derived relationships cannot be edited directly; edit the underlying stored facts"
                }
              >
                Edit Stored Fact
              </Button>
              <Button
                kind="danger"
                disabled={!isPrimaryStored}
                onClick={() => {
                  if (primaryEntry) {
                    setInitialDeleteMode(true);
                    setEditingEntry(primaryEntry);
                  }
                }}
                title={
                  isPrimaryStored
                    ? "Remove stored family fact"
                    : "Derived relationships cannot be removed directly; remove the underlying stored facts"
                }
              >
                Remove Stored Fact
              </Button>
              <Button onClick={() => setEditingPerson(selected)}>Edit Person</Button>
            </div>
          </aside>
        )}
      </div>

      {showAddFact && selected && (
        <AddRelationshipDialog
          sourcePerson={selected}
          peopleList={people}
          onClose={() => setShowAddFact(false)}
          onSaved={handleSavedMutation}
        />
      )}

      {editingEntry && selected && focusPersonObj && (
        <EditRelationshipDialog
          perspectivePerson={focusPersonObj}
          targetPerson={selected}
          entry={editingEntry}
          initialDeleteMode={initialDeleteMode}
          onClose={() => {
            setEditingEntry(null);
            setInitialDeleteMode(false);
          }}
          onSaved={handleSavedMutation}
        />
      )}

      {editingPerson && (
        <PersonEditorModal
          mode="edit"
          person={editingPerson}
          groups={groups}
          onClose={() => setEditingPerson(null)}
          onSaved={handleSavedMutation}
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

function RelationshipListDetailed({
  entries,
  onEditEntry,
  onDeleteEntry,
  onInspectProof,
}: {
  entries: RelationshipEntry[];
  onEditEntry?: (entry: RelationshipEntry) => void;
  onDeleteEntry?: (entry: RelationshipEntry) => void;
  onInspectProof?: (entry: RelationshipEntry) => void;
}) {
  return (
    <div className="relation-list">
      {entries.map((entry, index) => {
        const side = entry.side;
        const isStored = entry.derived === false;
        const storedKind = entry.stored_fact_kind;

        let provenanceLabel = isStored ? "Stored Fact" : "Derived Kinship Term";
        if (isStored && storedKind === "parent_child") {
          const kind = entry.kind && entry.kind !== "biological" ? ` (${entry.kind})` : "";
          provenanceLabel = `Parent-Child${kind}`;
        } else if (isStored && storedKind === "marriage") {
          const status = entry.status && entry.status !== "married" ? ` (${entry.status})` : "";
          provenanceLabel = `Marriage${status}`;
        } else if (isStored && storedKind === "sibling_group") {
          provenanceLabel = "Sibling Group";
        }

        return (
          <div
            className="relation-card-item"
            key={index}
            style={{
              marginBottom: 8,
              padding: "8px 10px",
              background: "var(--card-bg, #fff)",
              border: "1px solid var(--line, #e5e7eb)",
              borderRadius: 8,
            }}
          >
            <div className="relation-row" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span className="relation-en" style={{ fontWeight: 600 }}>{entry.label_en}</span>
              {entry.label_ur && (
                <span className="relation-ur" dir="rtl" lang="ur" style={{ fontWeight: 500 }}>
                  {entry.label_ur}
                </span>
              )}
            </div>
            <div className="family-badges">
              {side && (
                <span
                  className={`family-badge ${side === "maternal" ? "badge-maternal" : "badge-paternal"}`}
                >
                  {side.charAt(0).toUpperCase() + side.slice(1)}
                </span>
              )}
              <span className={`family-badge ${isStored ? "badge-stored" : "badge-derived"}`}>
                {provenanceLabel}
              </span>
            </div>
            {isStored ? (
              <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                {onEditEntry && (
                  <button
                    type="button"
                    className="btn btn-outline"
                    style={{ fontSize: 11.5, padding: "2px 8px" }}
                    onClick={() => onEditEntry(entry)}
                  >
                    Edit Stored Fact
                  </button>
                )}
                {onDeleteEntry && (
                  <button
                    type="button"
                    className="btn btn-danger"
                    style={{ fontSize: 11.5, padding: "2px 8px" }}
                    onClick={() => onDeleteEntry(entry)}
                  >
                    Remove Stored Fact
                  </button>
                )}
              </div>
            ) : (
              <div style={{ marginTop: 4 }}>
                <div className="muted tiny" style={{ marginBottom: 4 }}>
                  This relationship is derived from underlying family facts.
                </div>
                {onInspectProof && (
                  <button
                    type="button"
                    className="btn btn-outline"
                    style={{ fontSize: 11.5, padding: "2px 8px" }}
                    onClick={() => onInspectProof(entry)}
                  >
                    Inspect Proof
                  </button>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
