import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Avatar, Button, ErrorNote, Icon, PersonSearch } from "../components/ui";
import { JournalModal, useRelationship } from "../components/PersonDetail";
import { usePerspective } from "../state";
import type { Group, Person, RelationshipEntry } from "../types";
import { AddRelationshipDialog } from "../features/relationships/components/AddRelationshipDialog";
import { EditRelationshipDialog } from "../features/relationships/components/EditRelationshipDialog";
import { PersonEditorModal } from "../features/people/components/PersonEditorModal";
import { UndoBar } from "../features/mutations/components/UndoBar";
import { useTheme } from "../theme";
import mermaid from "mermaid";

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
  const { theme } = useTheme();
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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [selected, setSelected] = useState<Person | null>(null);
  const [zoom, setZoom] = useState(1);
  const [rendering, setRendering] = useState(false);
  const [showLegend, setShowLegend] = useState(true);
  const [searchOpen, setSearchOpen] = useState(false);
  const [immersive, setImmersive] = useState(false);
  const [nativeFullscreen, setNativeFullscreen] = useState(false);

  const diagramRef = useRef<HTMLDivElement>(null);
  const familyAreaRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement | null>(null);
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
      // api.people.list() remains authoritative for aliases, notes, groups,
      // and other inspector details. family.view intentionally returns only
      // the compact diagram projection.
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
    const viewport = container.closest<HTMLElement>(".family-canvas-wrap");
    if (!viewport) return;
    const nodeBounds = node.getBoundingClientRect();
    const viewportBounds = viewport.getBoundingClientRect();
    viewport.scrollTo({
      left: viewport.scrollLeft + nodeBounds.left - viewportBounds.left - (viewport.clientWidth - nodeBounds.width) / 2,
      top: viewport.scrollTop + nodeBounds.top - viewportBounds.top - (viewport.clientHeight - nodeBounds.height) / 2,
      behavior: "smooth",
    });
  }

  useEffect(() => {
    if (!diagram || !diagramRef.current) return;
    let cancelled = false;
    setRendering(true);
    renderCounter.current += 1;
    const container = diagramRef.current;
    const id = `pr-family-diagram-${renderCounter.current}`;

    const root = getComputedStyle(document.documentElement);
    const token = (name: string) => root.getPropertyValue(name).trim();
    mermaid.initialize({
      startOnLoad: false,
      theme: "base",
      securityLevel: "strict",
      themeVariables: {
        background: token("--graph-canvas"),
        primaryColor: token("--surface-primary"),
        primaryTextColor: token("--text-primary"),
        primaryBorderColor: token("--border-strong"),
        lineColor: token("--family-line"),
        secondaryColor: token("--accent-selected"),
        tertiaryColor: token("--surface-secondary"),
        fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
      },
      flowchart: {
        useMaxWidth: false,
        htmlLabels: true,
        curve: "basis",
        padding: 10,
      },
    });

    mermaid
      .render(id, diagram)
      .then(({ svg }) => {
        if (cancelled) return;
        container.innerHTML = svg;

        // Mermaid's generated class/style rules contain the legacy static
        // family-tree palette. Repaint the rendered SVG from the live design
        // tokens so a theme change updates every node and cluster without
        // changing the canonical Python-derived diagram or family facts.
        const setPaint = (element: SVGElement, property: "fill" | "stroke", value: string) => {
          element.style.setProperty(property, value, "important");
        };
        const paintShapes = (selector: string, fill: string, stroke: string) => {
          container.querySelectorAll<SVGElement>(selector).forEach((shape) => {
            setPaint(shape, "fill", fill);
            setPaint(shape, "stroke", stroke);
          });
        };
        const colorChannels = (value: string) => {
          const hex = value.match(/#([0-9a-f]{6})/i)?.[1];
          if (hex) return [0, 2, 4].map((offset) => Number.parseInt(hex.slice(offset, offset + 2), 16));
          const rgb = value.match(/rgba?\((\d+)[, ]+(\d+)[, ]+(\d+)/i);
          return rgb ? rgb.slice(1, 4).map(Number) : null;
        };

        paintShapes("g.node.person rect, g.node.person polygon, g.node.person path", token("--surface-primary"), token("--border-strong"));
        paintShapes("g.node.matperson rect, g.node.matperson polygon, g.node.matperson path", token("--maternal-bg"), token("--maternal"));
        paintShapes("g.node.patperson rect, g.node.patperson polygon, g.node.patperson path", token("--paternal-bg"), token("--paternal"));
        container.querySelectorAll<SVGElement>("g.node.focus rect, g.node.focus polygon, g.node.focus path").forEach((shape) => {
          setPaint(shape, "stroke", token("--accent-primary"));
        });
        container.querySelectorAll<SVGElement>("g.cluster rect").forEach((shape) => {
          const channels = colorChannels(shape.style.fill || shape.getAttribute("fill") || "");
          const [red, green, blue] = channels ?? [0, 0, 0];
          const maternal = red > blue + 4 && red >= green;
          const paternal = blue > red + 4 && blue >= green;
          setPaint(shape, "fill", token(maternal ? "--maternal-bg" : paternal ? "--paternal-bg" : "--surface-glass"));
          setPaint(shape, "stroke", token(maternal ? "--maternal" : paternal ? "--paternal" : "--border-subtle"));
        });
        container.querySelectorAll<HTMLElement>(".nodeLabel, .nodeLabel *, .cluster-label, .cluster-label *, .edgeLabel, .edgeLabel *").forEach((label) => {
          label.style.setProperty("color", token("--text-primary"), "important");
        });
        container.querySelectorAll<SVGElement>(".edgeLabel rect, .labelBkg").forEach((shape) => {
          setPaint(shape, "fill", token("--surface-elevated"));
        });
        container.querySelectorAll<SVGElement>(".edgePath path, .flowchart-link").forEach((shape) => {
          setPaint(shape, "stroke", token("--family-line"));
        });

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
  }, [diagram, people, currentFocusId, theme]);

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

  useEffect(() => {
    const syncFullscreenState = () => {
      const active = document.fullscreenElement === familyAreaRef.current;
      setNativeFullscreen(active);
      if (!document.fullscreenElement) setImmersive(false);
    };
    document.addEventListener("fullscreenchange", syncFullscreenState);
    return () => document.removeEventListener("fullscreenchange", syncFullscreenState);
  }, []);

  const exitImmersive = useCallback(async () => {
    if (document.fullscreenElement === familyAreaRef.current) {
      await document.exitFullscreen();
    }
    setNativeFullscreen(false);
    setImmersive(false);
  }, []);

  const toggleImmersive = useCallback(async () => {
    if (immersive || document.fullscreenElement === familyAreaRef.current) {
      await exitImmersive();
      return;
    }
    const familyArea = familyAreaRef.current;
    if (!familyArea) return;
    try {
      if (familyArea.requestFullscreen) {
        await familyArea.requestFullscreen();
        setNativeFullscreen(true);
      }
    } catch {
      // Desktop webviews may deny the Fullscreen API. The fixed-position
      // immersive fallback keeps the tree, inspector, and controls together.
    }
    setImmersive(true);
  }, [exitImmersive, immersive]);

  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && (immersive || nativeFullscreen)) {
        void exitImmersive();
      }
    };
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [exitImmersive, immersive, nativeFullscreen]);

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
    <div className="view family-view">
      <div className="view-head sr-only">
        <div>
          <h1>Family Tree / خاندانی شجرہ</h1>
          <p className="muted">
            Genealogical structure and lineage derived by Python kinship engine — labels follow focus.
          </p>
        </div>
      </div>

      <div
        ref={familyAreaRef}
        className={`family-layout ${immersive ? "is-immersive" : ""}`}
        data-immersive={immersive ? "true" : "false"}
      >
        <div className="family-canvas-wrap">
          <ErrorNote error={error} />
          {(loading || rendering) && <div className="state-box family-rendering-state">Rendering family diagram…</div>}
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

        <div className="family-focus-bar glass-panel">
          <span className="family-focus-label">Family focus</span>
          <div className="family-focus-current">
            {focusPersonObj && <Avatar person={focusPersonObj} size={28} />}
            <span>{focusPerson?.name ?? currentFocusId}</span>
          </div>
          {!isDefaultFocus && defaultFamilyFocusId && (
            <Button kind="ghost" className="family-return-focus" onClick={() => handleFocusChange(defaultFamilyFocusId)} title="Return to default viewer focus">
              <Icon name="target" /><span className="sr-only">Return to My Family View</span>
            </Button>
          )}
        </div>

        <div className="connections-search-dock family-search-dock">
          <div
            className={`relationships-search-wrap glass-panel ${searchOpen ? "open" : "collapsed"}`}
            onFocusCapture={() => setSearchOpen(true)}
          >
            <span className="connections-search-icon" aria-hidden="true"><Icon name="search" size={20} /></span>
            <PersonSearch
              people={people}
              onSelect={(person) => {
                handleFocusChange(person.id);
                setSearchOpen(false);
              }}
              placeholder="Search family focus…"
              ariaLabel="Search family focus by name or alias"
              inputRef={(node) => { searchInputRef.current = node; }}
              onOpenChange={setSearchOpen}
            />
            {searchOpen && (
              <Button kind="ghost" className="icon-button connections-search-close" onClick={() => {
                setSearchOpen(false);
                searchInputRef.current?.blur();
              }} ariaLabel="Close Family Tree search" title="Close search"><Icon name="close" /></Button>
            )}
          </div>
        </div>

        <div className="relationships-footer family-footer glass-panel" aria-label="Family tree controls and legend">
          <div className="graph-zoom-controls" aria-label="Family tree zoom controls">
            <Button className="graph-dock-button" ariaLabel="Zoom out" onClick={() => setZoom((v) => Math.max(0.3, +(v / 1.2).toFixed(2)))} title="Zoom out"><span className="graph-zoom-glyph" aria-hidden="true">−</span></Button>
            <output className="graph-zoom-value" aria-live="polite">{Math.round(zoom * 100)}%</output>
            <Button className="graph-dock-button" ariaLabel="Zoom in" onClick={() => setZoom((v) => Math.min(2.5, +(v * 1.2).toFixed(2)))} title="Zoom in"><span className="graph-zoom-glyph" aria-hidden="true">+</span></Button>
          </div>
          <Button className="graph-dock-button" ariaLabel="Fit diagram to viewport" onClick={handleFit} title="Fit diagram to viewport"><Icon name="fit" /></Button>
          <Button className="graph-dock-button" ariaLabel="Center focus person" onClick={handleCenterFocus} title="Center focus person"><Icon name="target" /></Button>
          <Button className="graph-dock-button" ariaLabel={immersive ? "Exit Family Tree fullscreen" : "Enter Family Tree fullscreen"} ariaPressed={immersive} onClick={() => void toggleImmersive()} title={immersive ? "Exit fullscreen" : "Enter fullscreen"}><Icon name="fullscreen" /></Button>
          <Button className="graph-dock-button" ariaLabel={showLegend ? "Hide Family Tree legend" : "Show Family Tree legend"} ariaExpanded={showLegend} onClick={() => setShowLegend((value) => !value)} title={showLegend ? "Hide legend" : "Show legend"}><Icon name="legend" /></Button>
          <Button className="graph-dock-button" disabled={loading || rendering} ariaLabel="Reload family tree" onClick={() => {
            void loadPeopleAndGroups();
            void loadFamilyData(currentFocusId);
          }} title="Reload family tree"><Icon name="reload" /></Button>
          {showLegend && (
            <>
              <span className="graph-dock-divider" aria-hidden="true" />
              <div className="family-dock-legend family-legend">
                <span className="legend-item"><span className="legend-swatch focus" /><span><strong>Focus</strong></span></span>
                <span className="legend-item"><span className="legend-swatch maternal" /><span>Maternal Branch</span></span>
                <span className="legend-item"><span className="legend-swatch paternal" /><span>Paternal Branch</span></span>
                <span className="legend-item"><span className="legend-swatch marriage" /><span>Marriage</span></span>
                <span className="legend-item"><span className="legend-swatch parent-child" /><span>Parent / child</span></span>
                <span className="legend-item"><span className="legend-swatch sibling" /><span>Sibling / cross link</span></span>
              </div>
            </>
          )}
        </div>

        {selected && (
          <aside className="family-side glass-panel">
            <div className="inspector-profile-row">
              <Avatar person={selected} size={60} />
              <div className="inspector-profile-copy">
                <strong>{selected.name}</strong>
                <div className="inspector-relationship-line">
                  {primaryEntry?.label_en ?? "Family connection"}
                  {primaryEntry?.label_ur && <span dir="rtl" lang="ur"> · {primaryEntry.label_ur}</span>}
                </div>
              </div>
              <Button kind="ghost" className="icon-button inspector-close" onClick={() => handleSelectPerson(null)} title="Close context panel" ariaLabel="Close family inspector">
                <Icon name="close" />
              </Button>
            </div>

            <div className="inspector-primary-actions">
              {onNavigateToProfile && <Button onClick={() => onNavigateToProfile(selected.id)}><Icon name="profile" /><span>View Profile</span><span className="inspector-chevron">›</span></Button>}
              <Button onClick={() => setJournalFor(selected)}><Icon name="journal" /><span>Journal</span><span className="inspector-chevron">›</span></Button>
              <Button onClick={() => handleFocusChange(selected.id)}><Icon name="path" /><span>View family from this person</span><span className="inspector-chevron">›</span></Button>
            </div>

            <div className="inspector-metadata">
              <div className="inspector-meta-row"><Icon name="profile" /><div><span>Full name</span><strong>{selected.name}</strong></div></div>
              <div className="inspector-meta-row"><Icon name="family" /><div><span>Relationship to {focusPerson?.name ?? "focus"}</span><strong>{primaryEntry?.label_en ?? "Not recorded"}</strong></div></div>
              <div className="inspector-meta-row"><Icon name="journal" /><div><span>Person details</span><strong>{selected.birth_year ? `Born ${selected.birth_year}` : "Birth year unknown"}{selected.gender ? ` · ${selected.gender}` : ""}</strong></div></div>
            </div>

            <details className="inspector-disclosure inspector-evidence">
              <summary><Icon name="path" /> Relationship evidence</summary>
              <div className="inspector-disclosure-body">
                {selectedRelationship.loading ? <div className="muted">Calculating relationship…</div> : selectedRelationship.error ? <ErrorNote error={selectedRelationship.error} /> : selectedRelationship.result ? (
                  <>
                    <RelationshipListDetailed entries={selectedRelationship.result.primary} onEditEntry={(entry) => { setInitialDeleteMode(false); setEditingEntry(entry); }} onDeleteEntry={(entry) => { setInitialDeleteMode(true); setEditingEntry(entry); }} onInspectProof={(entry) => { setInitialDeleteMode(false); setEditingEntry(entry); }} />
                    {selectedRelationship.result.additional.length > 0 && (
                      <div className="rel-multipath-callout">
                        <span className="family-badge badge-multipath">{selectedRelationship.result.additional.length + 1} family paths</span>
                        <RelationshipListDetailed entries={selectedRelationship.result.additional} onEditEntry={(entry) => { setInitialDeleteMode(false); setEditingEntry(entry); }} onDeleteEntry={(entry) => { setInitialDeleteMode(true); setEditingEntry(entry); }} onInspectProof={(entry) => { setInitialDeleteMode(false); setEditingEntry(entry); }} />
                      </div>
                    )}
                  </>
                ) : null}
              </div>
            </details>

            <details className="inspector-disclosure inspector-manage">
              <summary><Icon name="more" /> More actions</summary>
              <div className="inspector-disclosure-body inspector-manage-grid">
                {onNavigateToRelationships && <Button onClick={() => onNavigateToRelationships(selected.id, currentFocusId)}><Icon name="path" /> View in Connections<span className="sr-only"> View in Relationships</span></Button>}
                <Button kind="primary" onClick={() => setShowAddFact(true)}><Icon name="add" /> Add Family Fact</Button>
                <Button disabled={!isPrimaryStored} onClick={() => { if (primaryEntry) { setInitialDeleteMode(false); setEditingEntry(primaryEntry); } }} title={isPrimaryStored ? "Edit stored family fact" : "Derived relationships cannot be edited directly; edit the underlying stored facts"}><Icon name="edit" /> Edit Stored Fact</Button>
                <Button kind="danger" disabled={!isPrimaryStored} onClick={() => { if (primaryEntry) { setInitialDeleteMode(true); setEditingEntry(primaryEntry); } }} title={isPrimaryStored ? "Remove stored family fact" : "Derived relationships cannot be removed directly; remove the underlying stored facts"}>Remove Stored Fact</Button>
                <Button onClick={() => setEditingPerson(selected)}><Icon name="edit" /> Edit Person</Button>
              </div>
            </details>
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
              background: "var(--card-bg)",
              border: "1px solid var(--line)",
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
