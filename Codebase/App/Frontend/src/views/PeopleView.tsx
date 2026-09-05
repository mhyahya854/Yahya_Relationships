import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { PersonEditorModal } from "../features/people/components/PersonEditorModal";
import { UndoBar } from "../features/mutations/components/UndoBar";
import { CompareModal, JournalModal, PersonProfile } from "../components/PersonDetail";
import { Avatar, Button, ErrorNote, Modal } from "../components/ui";
import { usePerspective } from "../state";
import type { Group, Person, RelationshipEntry } from "../types";

interface Props {
  onNavigateToRelationships?: (personId: string) => void;
}

type SortOption = "name-asc" | "name-desc" | "birth-asc" | "birth-desc" | "relationship";

export function PeopleView({ onNavigateToRelationships }: Props) {
  const { perspectiveId, perspectivePerson, setPerspective } = usePerspective();
  const [people, setPeople] = useState<Person[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [groupFilter, setGroupFilter] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [sortBy, setSortBy] = useState<SortOption>("name-asc");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  // Perspective relationship mapping: target_id -> { primary, additional }
  const [perspectiveRelationships, setPerspectiveRelationships] = useState<
    Map<string, { primary: RelationshipEntry[]; additional: RelationshipEntry[] }>
  >(new Map());

  // Modal states
  const [selected, setSelected] = useState<Person | null>(null);
  const [personModalMode, setPersonModalMode] = useState<"add" | "edit" | "delete" | null>(null);
  const [personModalTarget, setPersonModalTarget] = useState<Person | null>(null);
  const [journalFor, setJournalFor] = useState<Person | null>(null);
  const [comparePicker, setComparePicker] = useState(false);
  const [compareTarget, setCompareTarget] = useState<Person | null>(null);
  const [undoNotice, setUndoNotice] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [peopleRes, groupsRes] = await Promise.all([
        api.people.list(),
        api.groups.list(),
      ]);
      setPeople(peopleRes.people);
      setGroups(groupsRes.groups);
      setError(null);
    } catch (err: unknown) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  // Load perspective relationship interpretations when perspectiveId changes
  useEffect(() => {
    if (!perspectiveId) {
      setPerspectiveRelationships(new Map());
      return;
    }
    let cancelled = false;
    api.relationships
      .from(perspectiveId)
      .then((res) => {
        if (cancelled) return;
        const map = new Map<string, { primary: RelationshipEntry[]; additional: RelationshipEntry[] }>();
        for (const item of res.relationships) {
          map.set(item.target.id, {
            primary: item.primary,
            additional: item.additional,
          });
        }
        setPerspectiveRelationships(map);
      })
      .catch(() => {
        // Non-fatal if relationships couldn't be derived
      });
    return () => {
      cancelled = true;
    };
  }, [perspectiveId]);

  const handleSaved = (desc: string) => {
    setUndoNotice(desc);
    void loadData();
  };

  const handleUndo = async () => {
    try {
      const res = await api.mutations.undo();
      if (res.ok) {
        setUndoNotice(null);
        await loadData();
      }
    } catch (err: unknown) {
      window.alert(err instanceof Error ? err.message : "Undo failed");
    }
  };

  // Group counts calculation (canonical people per group)
  const groupCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const p of people) {
      for (const g of p.groups) {
        counts[g.id] = (counts[g.id] || 0) + 1;
      }
    }
    return counts;
  }, [people]);

  // Filter and Search
  const filteredPeople = useMemo(() => {
    let result = people;

    // Filter by group
    if (groupFilter) {
      result = result.filter((p) => p.groups.some((g) => g.id === groupFilter));
    }

    // Local Search by name and aliases
    const q = query.trim().toLowerCase();
    if (q) {
      result = result.filter((p) => {
        if (p.name.toLowerCase().includes(q)) return true;
        if (p.aliases.some((a) => a.toLowerCase().includes(q))) return true;
        if (p.note_en && p.note_en.toLowerCase().includes(q)) return true;
        if (p.note_ur && p.note_ur.toLowerCase().includes(q)) return true;
        return false;
      });
    }

    // Sorting
    return [...result].sort((a, b) => {
      switch (sortBy) {
        case "name-asc":
          return a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
        case "name-desc":
          return b.name.localeCompare(a.name, undefined, { sensitivity: "base" });
        case "birth-asc": {
          const ya = a.birth_year ?? 9999;
          const yb = b.birth_year ?? 9999;
          return ya - yb;
        }
        case "birth-desc": {
          const ya = a.birth_year ?? -9999;
          const yb = b.birth_year ?? -9999;
          return yb - ya;
        }
        case "relationship": {
          const relA = perspectiveRelationships.get(a.id)?.primary?.[0]?.label_en || "zzz";
          const relB = perspectiveRelationships.get(b.id)?.primary?.[0]?.label_en || "zzz";
          return relA.localeCompare(relB);
        }
        default:
          return 0;
      }
    });
  }, [people, groupFilter, query, sortBy, perspectiveRelationships]);

  return (
    <div className="view">
      {/* HEADER */}
      <div className="view-head">
        <div>
          <h1>People</h1>
          <p className="muted">
            Personal relationship directory. {people.length} canonical {people.length === 1 ? "person" : "people"} recorded.
          </p>
        </div>
        <Button
          kind="primary"
          onClick={() => {
            setPersonModalTarget(null);
            setPersonModalMode("add");
          }}
        >
          + Add Person
        </Button>
      </div>

      <ErrorNote error={error} />

      {/* GROUP FILTER TABS WITH CANONICAL COUNTS */}
      <div className="tabs" style={{ marginBottom: 12, overflowX: "auto", flexWrap: "wrap" }}>
        <button
          type="button"
          className={`tab ${groupFilter === null ? "active" : ""}`}
          onClick={() => setGroupFilter(null)}
        >
          All ({people.length})
        </button>
        {groups.map((group) => {
          const count = groupCounts[group.id] || 0;
          return (
            <button
              type="button"
              key={group.id}
              className={`tab ${groupFilter === group.id ? "active" : ""}`}
              onClick={() => setGroupFilter(group.id)}
            >
              {group.name} ({count})
            </button>
          );
        })}
      </div>

      {/* TOOLBAR */}
      <div className="toolbar" style={{ gap: 10 }}>
        <input
          className="text-input grow"
          value={query}
          placeholder="Search by name or alias (e.g. Mansoor, Uncle, منصور)…"
          onChange={(event) => setQuery(event.target.value)}
        />

        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span className="muted small">Sort:</span>
          <select
            className="select-input"
            value={sortBy}
            onChange={(event) => setSortBy(event.target.value as SortOption)}
          >
            <option value="name-asc">Name (A → Z)</option>
            <option value="name-desc">Name (Z → A)</option>
            <option value="relationship">Relationship to perspective</option>
            <option value="birth-asc">Birth Year (Oldest first)</option>
            <option value="birth-desc">Birth Year (Youngest first)</option>
          </select>
        </div>

        {(query || groupFilter) && (
          <Button
            kind="ghost"
            onClick={() => {
              setQuery("");
              setGroupFilter(null);
            }}
          >
            Clear filters
          </Button>
        )}
      </div>

      {/* LOADING STATE */}
      {loading && people.length === 0 && (
        <div className="muted" style={{ padding: "40px 0", textAlign: "center" }}>
          Loading relationship index…
        </div>
      )}

      {/* PEOPLE TABLE */}
      <div className="people-table">
        <div className="people-table-head" style={{ gridTemplateColumns: "1.6fr 1.3fr 1fr 1.2fr 160px" }}>
          <span>Person</span>
          <span>Relationship to Perspective</span>
          <span>Aliases</span>
          <span>Groups</span>
          <span>Actions</span>
        </div>

        {filteredPeople.map((person) => {
          const relData = perspectiveRelationships.get(person.id);
          const isSelf = person.id === perspectiveId;
          const primaryRel = isSelf
            ? { label_en: "Self", label_ur: "خود" }
            : relData?.primary?.[0];
          const hasAdditional = !isSelf && (relData?.additional?.length || 0) > 0;

          return (
            <div
              className="people-table-row"
              key={person.id}
              style={{ gridTemplateColumns: "1.6fr 1.3fr 1fr 1.2fr 160px" }}
            >
              {/* Person Name & Bio */}
              <button
                type="button"
                className="person-cell"
                onClick={() => setSelected(person)}
                title={`Open profile for ${person.name}`}
              >
                <Avatar person={person} size={32} />
                <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>
                  <strong>{person.name}</strong>
                  {person.journal_exists === false && (
                    <span title="Canonical journal missing from disk" style={{ color: "#d97706", marginLeft: 6, fontSize: 13 }}>⚠</span>
                  )}
                  <span className="muted tiny" style={{ display: "block" }}>
                    {person.birth_year ? `b. ${person.birth_year}` : ""}{" "}
                    {person.gender && person.gender !== "unknown" ? `· ${person.gender}` : ""}
                  </span>
                </span>

              </button>

              {/* Perspective Relationship Badge */}
              <div style={{ display: "flex", alignItems: "center", gap: 6, overflow: "hidden" }}>
                {primaryRel ? (
                  <span
                    className="chip"
                    style={{
                      background: isSelf ? "var(--ok-soft)" : "var(--accent-soft)",
                      color: isSelf ? "var(--ok)" : "var(--accent-strong)",
                      fontWeight: 600,
                      fontSize: 12,
                      border: "1px solid var(--line)",
                    }}
                  >
                    {primaryRel.label_en}
                    {primaryRel.label_ur ? ` / ${primaryRel.label_ur}` : ""}
                    {hasAdditional ? " (+1)" : ""}
                  </span>
                ) : (
                  <span className="muted tiny">—</span>
                )}
              </div>

              {/* Aliases */}
              <span className="muted small" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {person.aliases.join(", ") || "—"}
              </span>

              {/* Group Chips */}
              <span className="group-chips" style={{ overflow: "hidden" }}>
                {person.groups.slice(0, 2).map((group) => (
                  <span className="chip chip-group" key={group.id} title={group.is_primary ? "Primary folder" : undefined}>
                    {group.name}
                  </span>
                ))}
                {person.groups.length > 2 && (
                  <span className="chip">+{person.groups.length - 2}</span>
                )}
              </span>

              {/* Actions */}
              <span
                className="row-actions"
                onClick={(e) => e.stopPropagation()}
                style={{ justifyContent: "flex-end" }}
              >
                <Button kind="ghost" onClick={() => setSelected(person)}>
                  Profile
                </Button>
                <Button
                  kind="ghost"
                  onClick={() => {
                    setPersonModalTarget(person);
                    setPersonModalMode("edit");
                  }}
                >
                  Edit
                </Button>
                <Button
                  kind="danger"
                  onClick={() => {
                    setPersonModalTarget(person);
                    setPersonModalMode("delete");
                  }}
                  title="Remove person safely"
                >
                  Delete
                </Button>
              </span>
            </div>
          );
        })}

        {/* EMPTY STATES */}
        {!loading && filteredPeople.length === 0 && (
          <div className="empty-state" style={{ padding: "40px 20px", textAlign: "center" }}>
            {query ? (
              <>
                <p style={{ margin: "0 0 12px", color: "var(--muted)", fontSize: 15 }}>
                  No people found matching <strong>"{query}"</strong>.
                </p>
                <Button kind="default" onClick={() => setQuery("")}>
                  Clear search
                </Button>
              </>
            ) : groupFilter ? (
              <>
                <p style={{ margin: "0 0 12px", color: "var(--muted)", fontSize: 15 }}>
                  No people belong to this group yet.
                </p>
                <Button
                  kind="primary"
                  onClick={() => {
                    setPersonModalTarget(null);
                    setPersonModalMode("add");
                  }}
                >
                  + Add Person
                </Button>
              </>
            ) : (
              <p style={{ margin: 0, color: "var(--muted)" }}>No people recorded yet.</p>
            )}
          </div>
        )}
      </div>

      {/* PERSON PROFILE MODAL */}
      {selected && (
        <Modal title={`${selected.name} — Profile`} onClose={() => setSelected(null)} wide>
          <PersonProfile
            person={selected}
            perspectiveId={perspectiveId}
            perspectiveName={perspectivePerson?.name}
            onViewFrom={(personId) => void setPerspective(personId)}
            onCompare={() => setComparePicker(true)}
            onEdit={(p) => {
              setPersonModalTarget(p);
              setPersonModalMode("edit");
            }}
            onDelete={(p) => {
              setPersonModalTarget(p);
              setPersonModalMode("delete");
            }}
            onOpenPerson={(personId) => {
              const target = people.find((p) => p.id === personId);
              if (target) {
                setSelected(target);
              }
            }}
            onShowRelationshipPath={(personId) => {
              setSelected(null);
              onNavigateToRelationships?.(personId);
            }}
            onOpenJournal={() => setJournalFor(selected)}
          />
        </Modal>
      )}

      {/* PERSON EDITOR MODAL (ADD / EDIT / DELETE) */}
      {personModalMode && (
        <PersonEditorModal
          mode={personModalMode}
          person={personModalTarget}
          groups={groups}
          onClose={() => {
            setPersonModalMode(null);
            setPersonModalTarget(null);
          }}
          onSaved={handleSaved}
          onOpenExisting={(existingId) => {
            const match = people.find((p) => p.id === existingId);
            if (match) {
              setSelected(match);
            }
          }}
        />
      )}

      {/* STANDALONE JOURNAL MODAL */}
      {journalFor && (
        <JournalModal person={journalFor} onClose={() => setJournalFor(null)} />
      )}

      {/* COMPARE PICKER MODAL */}
      {comparePicker && selected && (
        <Modal title={`Compare ${selected.name} with…`} onClose={() => setComparePicker(false)}>
          <div className="compare-picker">
            <input
              className="text-input"
              placeholder="Search person to compare with…"
              autoFocus
              onChange={(event) => {
                const q = event.target.value.toLowerCase().trim();
                if (!q) return;
                const match = people.find((person) => {
                  if (person.id === selected.id) return false;
                  const haystack = [person.name, ...person.aliases].join(" ").toLowerCase();
                  return haystack.includes(q);
                });
                if (match) {
                  setCompareTarget(match);
                  setComparePicker(false);
                }
              }}
            />
            <div className="people-pick-list" style={{ marginTop: 12, maxHeight: 300, overflowY: "auto" }}>
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
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      width: "100%",
                      padding: "8px 12px",
                      textAlign: "left",
                      border: "none",
                      background: "transparent",
                      cursor: "pointer",
                      borderRadius: 6,
                    }}
                  >
                    <Avatar person={person} size={24} />
                    <span>{person.name}</span>
                  </button>
                ))}
            </div>
          </div>
        </Modal>
      )}

      {/* COMPARE RESULT MODAL */}
      {compareTarget && selected && (
        <CompareModal
          a={selected.id}
          b={compareTarget.id}
          onClose={() => setCompareTarget(null)}
          onViewFrom={(personId) => void setPerspective(personId)}
        />
      )}

      {/* UNDO NOTIFICATION BAR */}
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
