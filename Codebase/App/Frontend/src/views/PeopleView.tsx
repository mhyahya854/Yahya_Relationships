import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { PersonEditorModal } from "../features/people/components/PersonEditorModal";
import { UndoBar } from "../features/mutations/components/UndoBar";
import {
  JournalModal,
  PersonProfile,
  CompareModal,
  useRelationship,
} from "../components/PersonDetail";
import {
  Avatar,
  Button,
  ErrorNote,
  Modal,
  RelationshipEntryList,
} from "../components/ui";
import { usePerspective } from "../state";
import type { Group, Person, RelationshipResult } from "../types";

export function PeopleView() {
  const { perspectiveId, setPerspective } = usePerspective();
  const [people, setPeople] = useState<Person[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [groupFilter, setGroupFilter] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [selected, setSelected] = useState<Person | null>(null);
  const [personModalMode, setPersonModalMode] = useState<"add" | "edit" | "delete" | null>(null);
  const [personModalTarget, setPersonModalTarget] = useState<Person | null>(null);
  const [journalFor, setJournalFor] = useState<Person | null>(null);
  const [comparePicker, setComparePicker] = useState(false);
  const [compareTarget, setCompareTarget] = useState<Person | null>(null);
  const [undoNotice, setUndoNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const result = await api.people.list(query || undefined, groupFilter ?? undefined);
      setPeople(result.people);
      const groupResult = await api.groups.list();
      setGroups(groupResult.groups);
      setError(null);
    } catch (err) {
      setError(err);
    }
  }, [query, groupFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleSaved = (desc: string) => {
    setUndoNotice(desc);
    void load();
  };

  const handleUndo = async () => {
    try {
      const res = await api.mutations.undo();
      if (res.ok) {
        setUndoNotice(null);
        await load();
      }
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Undo failed");
    }
  };

  const relationship = useRelationship(
    selected ? perspectiveId : null,
    selected ? selected.id : null,
  );

  return (
    <div className="view">
      <div className="view-head">
        <div>
          <h1>People</h1>
          <p className="muted">
            One canonical record per real person. Manage people, aliases, groups, and folders safely.
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
      <div className="toolbar">
        <input
          className="text-input grow"
          value={query}
          placeholder="Search by name or alias…"
          onChange={(event) => setQuery(event.target.value)}
        />
        <select
          className="select-input"
          value={groupFilter ?? ""}
          onChange={(event) => setGroupFilter(event.target.value || null)}
        >
          <option value="">All groups</option>
          {groups.map((group) => (
            <option key={group.id} value={group.id}>
              {group.name} ({group.member_count})
            </option>
          ))}
        </select>
      </div>
      <div className="people-table">
        <div className="people-table-head">
          <span>Person</span>
          <span>Aliases</span>
          <span>Groups</span>
          <span>Actions</span>
        </div>
        {people.map((person) => (
          <div className="people-table-row" key={person.id}>
            <button
              type="button"
              className="person-cell"
              onClick={() => setSelected(person)}
            >
              <Avatar person={person} size={30} />
              <span>
                <strong>{person.name}</strong>
                <span className="muted tiny">
                  {person.birth_year ? `b. ${person.birth_year}` : ""}{" "}
                  {person.gender ? `· ${person.gender}` : ""}
                </span>
              </span>
            </button>
            <span className="muted small">
              {person.aliases.join(", ") || "—"}
            </span>
            <span className="group-chips">
              {person.groups.slice(0, 2).map((group) => (
                <span className="chip chip-group" key={group.id}>
                  {group.name}
                </span>
              ))}
              {person.groups.length > 2 && (
                <span className="chip">+{person.groups.length - 2}</span>
              )}
            </span>
            <span className="row-actions">
              <Button kind="ghost" onClick={() => setSelected(person)}>
                Details
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
                title="Delete person safely"
              >
                Delete
              </Button>
            </span>
          </div>
        ))}
        {people.length === 0 && (
          <div className="empty-state">No people match this filter.</div>
        )}
      </div>

      {selected && (
        <Modal title="Person details" onClose={() => setSelected(null)} wide>
          <PersonProfile
            person={selected}
            onViewFrom={(personId) => void setPerspective(personId)}
            onCompare={() => setComparePicker(true)}
            onOpenJournal={(personId) => setJournalFor(selected)}
          />
          <div className="modal-rule" />
          <h3>Relationship from the current perspective</h3>
          {relationship.loading ? (
            <div className="muted">Calculating…</div>
          ) : relationship.error ? (
            <ErrorNote error={relationship.error} />
          ) : relationship.result ? (
            <RelationshipSummaryInline result={relationship.result} />
          ) : null}
        </Modal>
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
          onSaved={handleSaved}
        />
      )}

      {journalFor && (
        <JournalModal person={journalFor} onClose={() => setJournalFor(null)} />
      )}

      {comparePicker && selected && (
        <Modal title={`Compare ${selected.name} with…`} onClose={() => setComparePicker(false)}>
          <div className="compare-picker">
            <input
              className="text-input"
              placeholder="Type to filter people…"
              onChange={(event) => {
                const q = event.target.value.toLowerCase();
                const match = people.find((person) => {
                  if (person.id === selected.id) return false;
                  const haystack = [person.name, ...person.aliases]
                    .join(" ")
                    .toLowerCase();
                  return haystack.includes(q);
                });
                if (match) {
                  setCompareTarget(match);
                  setComparePicker(false);
                }
              }}
            />
            <div className="people-pick-list">
              {people
                .filter((person) => person.id !== selected.id)
                .slice(0, 40)
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

function RelationshipSummaryInline({ result }: { result: RelationshipResult }) {
  return (
    <div>
      <div className="rel-section-title">Primary</div>
      <RelationshipEntryList entries={result.primary} />
      {result.additional.length > 0 && (
        <>
          <div className="rel-section-title">Additional paths</div>
          <RelationshipEntryList entries={result.additional} />
        </>
      )}
    </div>
  );
}
