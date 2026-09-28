import type { DragEvent, ReactNode } from "react";
import { Avatar, Button } from "../../../components/ui";
import type { Person } from "../../../types";

export const CONNECTIONS_PERSON_DRAG_TYPE = "application/x-people-relationships-person";

export interface ImmediateConnection {
  person: Person;
  label?: string;
}

function dragPerson(event: DragEvent<HTMLElement>, personId: string) {
  event.dataTransfer.setData(CONNECTIONS_PERSON_DRAG_TYPE, personId);
  event.dataTransfer.setData("text/plain", personId);
  event.dataTransfer.effectAllowed = "copyMove";
}

function PersonChip({
  person,
  label,
  onInfo,
  onRemove,
}: {
  person: Person;
  label?: string;
  onInfo: () => void;
  onRemove?: () => void;
}) {
  return (
    <div
      className="relationship-builder-person"
      draggable
      onDragStart={(event) => dragPerson(event, person.id)}
    >
      <Avatar person={person} size={31} />
      <span className="relationship-builder-person-copy">
        <strong>{person.name}</strong>
        {label && <small>{label}</small>}
      </span>
      <button
        type="button"
        className="builder-info-button"
        onClick={onInfo}
        aria-label={`Information for ${person.name}`}
        title={`Information for ${person.name}`}
      >
        ⓘ
      </button>
      {onRemove && (
        <button
          type="button"
          className="builder-remove-button"
          onClick={onRemove}
          aria-label={`Remove ${person.name} from TO`}
          title={`Remove ${person.name} from TO`}
        >
          ×
        </button>
      )}
    </div>
  );
}

export function RelationshipBuilder({
  fromPerson,
  targets,
  selectedPerson,
  immediateConnections,
  pathContent,
  showReturnToPerspective,
  onReturnToPerspective,
  onSetFrom,
  onAddTo,
  onRemoveTo,
  onSelect,
  onInfo,
  onClearTargets,
  onDropPerson,
}: {
  fromPerson: Person | null;
  targets: Person[];
  selectedPerson: Person | null;
  immediateConnections: ImmediateConnection[];
  pathContent: ReactNode;
  showReturnToPerspective: boolean;
  onReturnToPerspective: () => void;
  onSetFrom: (person: Person) => void;
  onAddTo: (person: Person) => void;
  onRemoveTo: (personId: string) => void;
  onSelect: (person: Person) => void;
  onInfo: (person: Person) => void;
  onClearTargets: () => void;
  onDropPerson: (zone: "from" | "to", personId: string) => void;
}) {
  const handleDrop = (zone: "from" | "to") => (event: DragEvent<HTMLElement>) => {
    event.preventDefault();
    const personId = event.dataTransfer.getData(CONNECTIONS_PERSON_DRAG_TYPE)
      || event.dataTransfer.getData("text/plain");
    if (personId) onDropPerson(zone, personId);
  };
  const selectedIsFrom = selectedPerson?.id === fromPerson?.id;
  const selectedIsTarget = Boolean(
    selectedPerson && targets.some((person) => person.id === selectedPerson.id),
  );

  return (
    <aside
      className="relationships-panel connection-builder glass-panel"
      aria-label="Relationship Builder"
    >
      <header className="connection-builder-head">
        <div>
          <strong>Relationship Builder</strong>
          <span>Explore direct context, then trace selected routes.</span>
        </div>
        {targets.length > 0 && (
          <Button kind="ghost" onClick={onClearTargets}>Clear TO</Button>
        )}
      </header>

      <section className="builder-zone builder-from-zone">
        <div className="builder-zone-label">
          <span>FROM</span>
          {showReturnToPerspective && (
            <button type="button" onClick={onReturnToPerspective}>
              Return to My Perspective
            </button>
          )}
        </div>
        <div
          className="builder-drop-zone"
          data-person-drop-zone="from"
          onDragOver={(event) => event.preventDefault()}
          onDrop={handleDrop("from")}
        >
          {fromPerson ? (
            <PersonChip person={fromPerson} onInfo={() => onInfo(fromPerson)} />
          ) : (
            <span className="empty-inline">Choose one person as the origin.</span>
          )}
        </div>
        <small className="builder-help">Exactly one person. Dropping another person replaces FROM.</small>
      </section>

      <section className="builder-zone builder-to-zone">
        <div className="builder-zone-label">
          <span>TO</span>
          <small>{targets.length ? `${targets.length} target${targets.length === 1 ? "" : "s"}` : "0 targets"}</small>
        </div>
        <div
          className="builder-drop-zone builder-to-drop-zone"
          data-person-drop-zone="to"
          onDragOver={(event) => event.preventDefault()}
          onDrop={handleDrop("to")}
        >
          {targets.map((person) => (
            <PersonChip
              key={person.id}
              person={person}
              onInfo={() => onInfo(person)}
              onRemove={() => onRemoveTo(person.id)}
            />
          ))}
          <span className="builder-drop-hint">+ Drop another person here</span>
        </div>
        <small className="builder-help">Zero or many targets. This changes only the current exploration.</small>
      </section>

      {selectedPerson && !selectedIsFrom && (
        <section className="builder-selection-actions" aria-label={`Actions for ${selectedPerson.name}`}>
          <span>Selected: <strong>{selectedPerson.name}</strong></span>
          <div>
            <Button kind="ghost" onClick={() => onSetFrom(selectedPerson)}>Set as FROM</Button>
            {selectedIsTarget ? (
              <Button kind="ghost" onClick={() => onRemoveTo(selectedPerson.id)}>Remove from TO</Button>
            ) : (
              <Button kind="primary" onClick={() => onAddTo(selectedPerson)}>Add to TO</Button>
            )}
          </div>
        </section>
      )}

      {targets.length > 0 ? (
        <section className="builder-paths" aria-label="Relationship paths">
          <div className="builder-zone-label"><span>RELATIONSHIP PATHS</span></div>
          {pathContent}
        </section>
      ) : (
        <section className="builder-immediate-list" aria-label="Immediate direct relationships">
          <div className="builder-zone-label"><span>IMMEDIATE CONNECTIONS</span></div>
          <p>Only people directly connected to FROM are on the canvas.</p>
          <div className="builder-connection-list">
            {immediateConnections.map(({ person, label }) => (
              <div
                className="builder-connection-row"
                key={person.id}
                draggable
                onDragStart={(event) => dragPerson(event, person.id)}
              >
                <button type="button" onClick={() => onSelect(person)}>
                  <Avatar person={person} size={24} />
                  <span><strong>{person.name}</strong>{label && <small>{label}</small>}</span>
                </button>
                <button
                  type="button"
                  className="builder-info-button"
                  onClick={() => onInfo(person)}
                  aria-label={`Information for ${person.name}`}
                  title={`Information for ${person.name}`}
                >
                  ⓘ
                </button>
                <button
                  type="button"
                  className="builder-add-target"
                  onClick={() => onAddTo(person)}
                  aria-label={`Add ${person.name} to TO`}
                  title={`Add ${person.name} to TO`}
                >
                  +
                </button>
              </div>
            ))}
          </div>
        </section>
      )}
    </aside>
  );
}
