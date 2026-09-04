import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Avatar, Button, ErrorNote } from "../components/ui";
import { JournalModal, useRelationship } from "../components/PersonDetail";
import { usePerspective } from "../state";
import type { Group, Person } from "../types";
import { AddRelationshipDialog } from "../features/relationships/components/AddRelationshipDialog";
import { PersonEditorModal } from "../features/people/components/PersonEditorModal";
import { UndoBar } from "../features/mutations/components/UndoBar";
import mermaid from "mermaid";

mermaid.initialize({
  startOnLoad: false,
  theme: "neutral",
  securityLevel: "loose",
  flowchart: {
    useMaxWidth: false,
    htmlLabels: true,
    curve: "basis",
    padding: 10,
  },
});

export function FamilyView() {
  const { perspectiveId, perspectivePerson, setPerspective } = usePerspective();
  const [people, setPeople] = useState<Person[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [diagram, setDiagram] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [selected, setSelected] = useState<Person | null>(null);
  const [zoom, setZoom] = useState(1);
  const [rendering, setRendering] = useState(false);
  const diagramRef = useRef<HTMLDivElement>(null);
  const renderCounter = useRef(0);
  const [journalFor, setJournalFor] = useState<Person | null>(null);

  // Editor Dialog States
  const [showAddFact, setShowAddFact] = useState(false);
  const [editingPerson, setEditingPerson] = useState<Person | null>(null);
  const [undoNotice, setUndoNotice] = useState<string | null>(null);

  const loadPeopleAndGroups = useCallback(async () => {
    try {
      const result = await api.people.list();
      setPeople(result.people);
      const gRes = await api.groups.list();
      setGroups(gRes.groups);
    } catch (err) {
      setError(err);
    }
  }, []);

  const loadDiagram = useCallback(async () => {
    if (!perspectiveId) return;
    setLoading(true);
    setError(null);
    try {
      const result = await api.family.diagram(perspectiveId);
      setDiagram(result.mermaid);
      setZoom(1);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [perspectiveId]);

  useEffect(() => {
    void loadPeopleAndGroups();
  }, [loadPeopleAndGroups]);

  useEffect(() => {
    void loadDiagram();
  }, [loadDiagram]);

  const handleSavedMutation = async (desc: string) => {
    setUndoNotice(desc);
    await loadPeopleAndGroups();
    await loadDiagram();
  };

  const handleUndo = async () => {
    try {
      const res = await api.mutations.undo();
      if (res.ok) {
        setUndoNotice(null);
        await loadPeopleAndGroups();
        await loadDiagram();
      }
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Undo failed");
    }
  };

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
        container.querySelectorAll<SVGElement>('g.node[id^="flowchart-p_"]').forEach((node) => {
          const match = node.id.match(/^flowchart-(p_.+)-\d+$/);
          if (!match) return;
          const personId = match[1].replace(/^p_/, "");
          node.classList.add("clickable-node");
          node.addEventListener("click", () => {
            const person = people.find((entry) => entry.id === personId);
            if (person) {
              setSelected(person);
              highlightNode(container, personId);
            }
          });
          node.addEventListener("dblclick", () => {
            const person = people.find((entry) => entry.id === personId);
            if (person) void setPerspective(person.id);
          });
        });
        setSelected(null);
      })
      .catch((err: unknown) => setError(err))
      .finally(() => {
        if (!cancelled) setRendering(false);
      });
    return () => {
      cancelled = true;
    };
  }, [diagram, people, setPerspective]);

  useEffect(() => {
    if (selected && diagramRef.current) {
      highlightNode(diagramRef.current, selected.id);
    }
  }, [selected]);

  function highlightNode(container: HTMLElement, personId: string) {
    container.querySelectorAll(".family-highlight").forEach((node) => {
      node.classList.remove("family-highlight");
    });
    const node = container.querySelector<SVGElement>(
      `g.node[id^="flowchart-p_${personId}-"]`,
    );
    if (!node) return;
    node.classList.add("family-highlight");
    try {
      node.scrollIntoView({ block: "center", inline: "center" });
    } catch {
      node.scrollIntoView();
    }
  }

  const selectedRelationship = useRelationship(
    selected ? perspectiveId : null,
    selected ? selected.id : null,
  );

  return (
    <div className="view">
      <div className="view-head">
        <div>
          <h1>Family Diagram</h1>
          <p className="muted">
            Canonical family structure derived by Python kinship engine — labels follow perspective.
          </p>
        </div>
        <div className="family-controls">
          {selected && (
            <>
              <Button kind="primary" onClick={() => setShowAddFact(true)}>
                + Add Family Fact
              </Button>
              <Button onClick={() => setEditingPerson(selected)}>
                Edit Person
              </Button>
            </>
          )}
          <Button disabled={loading || rendering} onClick={() => void loadDiagram()}>
            Reload
          </Button>
          <Button onClick={() => setZoom((value) => Math.min(2.5, value * 1.2))}>
            + Zoom
          </Button>
          <Button onClick={() => setZoom((value) => Math.max(0.4, value / 1.2))}>
            − Zoom
          </Button>
        </div>
      </div>
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
            <div className="side-profile-row">
              <Avatar person={selected} size={42} />
              <div>
                <strong>{selected.name}</strong>
                {selected.groups[0] && (
                  <div className="muted tiny">{selected.groups[0].name}</div>
                )}
              </div>
            </div>
            <div className="family-side-note">
              Click a card to select it. Double-click any card to view the whole family from that person.
            </div>

            <div className="row-actions" style={{ marginBottom: 12 }}>
              <Button kind="primary" onClick={() => setShowAddFact(true)}>
                + Add Family Fact
              </Button>
              <Button onClick={() => setEditingPerson(selected)}>
                Edit Person
              </Button>
            </div>

            <h3>
              Relationship to {perspectivePerson?.name}
            </h3>
            {selectedRelationship.loading ? (
              <div className="muted">Calculating…</div>
            ) : selectedRelationship.error ? (
              <ErrorNote error={selectedRelationship.error} />
            ) : selectedRelationship.result ? (
              <>
                <div className="rel-section-title">Primary</div>
                <RelationshipListInline
                  entries={selectedRelationship.result.primary}
                />
                {selectedRelationship.result.additional.length > 0 && (
                  <>
                    <div className="rel-section-title">Additional paths</div>
                    <RelationshipListInline
                      entries={selectedRelationship.result.additional}
                    />
                  </>
                )}
              </>
            ) : null}
            <div className="row-actions family-side-actions">
              <Button
                kind="primary"
                onClick={() => void setPerspective(selected.id)}
              >
                View from this person
              </Button>
              <Button onClick={() => setJournalFor(selected)}>Journal</Button>
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

function RelationshipListInline({
  entries,
}: {
  entries: Array<{ label_en: string; label_ur?: string | null }>;
}) {
  return (
    <div className="relation-list">
      {entries.map((entry, index) => (
        <div className="relation-row" key={index}>
          <span className="relation-en">{entry.label_en}</span>
          {entry.label_ur && (
            <span className="relation-ur" dir="rtl" lang="ur">
              {entry.label_ur}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
