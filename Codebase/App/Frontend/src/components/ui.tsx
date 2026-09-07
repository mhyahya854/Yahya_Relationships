import {
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type RefCallback,
} from "react";
import { initialsOf } from "../markdown";
import type { Person } from "../types";

export function Button({
  children,
  onClick,
  kind = "default",
  disabled,
  title,
  type = "button",
}: {
  children: ReactNode;
  onClick?: () => void;
  kind?: "default" | "primary" | "danger" | "ghost";
  disabled?: boolean;
  title?: string;
  type?: "button" | "submit";
}) {
  return (
    <button
      type={type}
      className={`btn btn-${kind}`}
      onClick={onClick}
      disabled={disabled}
      title={title}
    >
      {children}
    </button>
  );
}

export function Avatar({ person, size = 34 }: { person: Person; size?: number }) {
  return (
    <span
      className="avatar"
      style={{ width: size, height: size, fontSize: size * 0.38 }}
      title={person.name}
    >
      {initialsOf(person.name)}
    </span>
  );
}

export function Modal({
  title,
  children,
  onClose,
  wide,
  closeOnEscape = false,
}: {
  title: ReactNode;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
  closeOnEscape?: boolean;
}) {
  return (
    <div
      className="modal-backdrop"
      onMouseDown={onClose}
      onKeyDown={(event) => {
        if (closeOnEscape && event.key === "Escape") onClose();
      }}
    >
      <div
        className={`modal ${wide ? "modal-wide" : ""}`}
        onMouseDown={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === "string" ? title : "Dialog"}
      >
        <div className="modal-head">
          <h2>{title}</h2>
          <Button kind="ghost" onClick={onClose} title="Close">
            ✕
          </Button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  const message =
    error instanceof Error ? error.message : "An unknown error occurred.";
  return <div className="error-note">{message}</div>;
}

export function PersonSearch({
  people,
  onSelect,
  placeholder,
  autoFocus,
  inputRef,
  ariaLabel,
  disabled,
}: {
  people: Person[];
  onSelect: (person: Person) => void;
  placeholder?: string;
  autoFocus?: boolean;
  inputRef?: RefCallback<HTMLInputElement>;
  ariaLabel?: string;
  disabled?: boolean;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const boxRef = useRef<HTMLDivElement>(null);

  const matches = (query.trim()
    ? people.filter((person) => {
        const haystack = [person.name, ...(person.aliases || [])]
          .join(" ")
          .toLowerCase();
        return haystack.includes(query.trim().toLowerCase());
      })
    : people
  ).slice(0, 20);

  useEffect(() => {
    function handleClick(event: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(event.target as Node)) {
        setOpen(false);
        setActiveIndex(-1);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const handleSelectPerson = (person: Person) => {
    onSelect(person);
    setQuery("");
    setOpen(false);
    setActiveIndex(-1);
  };

  return (
    <div className="person-search" ref={boxRef}>
      <input
        ref={inputRef}
        value={query}
        autoFocus={autoFocus}
        placeholder={placeholder ?? "Search people…"}
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={open}
        aria-label={ariaLabel ?? placeholder ?? "Search people"}
        aria-controls="person-search-listbox"
        disabled={disabled}
        aria-activedescendant={
          activeIndex >= 0 && matches[activeIndex]
            ? `person-opt-${matches[activeIndex].id}`
            : undefined
        }
        onChange={(event) => {
          setQuery(event.target.value);
          setOpen(true);
          setActiveIndex(-1);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setOpen(true);
            setActiveIndex((prev) =>
              matches.length === 0 ? -1 : prev + 1 < matches.length ? prev + 1 : 0,
            );
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setOpen(true);
            setActiveIndex((prev) =>
              matches.length === 0 ? -1 : prev - 1 >= 0 ? prev - 1 : matches.length - 1,
            );
          } else if (event.key === "Enter") {
            event.preventDefault();
            if (activeIndex >= 0 && activeIndex < matches.length) {
              handleSelectPerson(matches[activeIndex]);
            } else if (matches.length === 1) {
              handleSelectPerson(matches[0]);
            }
          } else if (event.key === "Escape") {
            setOpen(false);
            setActiveIndex(-1);
          }
        }}
      />
      {open && (
        <div className="person-search-results" role="listbox" id="person-search-listbox">
          {matches.length === 0 && (
            <div className="person-search-empty">No matches</div>
          )}
          {matches.map((person, index) => {
            const isMatchActive = index === activeIndex;
            return (
              <button
                type="button"
                role="option"
                id={`person-opt-${person.id}`}
                aria-selected={isMatchActive}
                key={person.id}
                className={`person-search-row ${isMatchActive ? "active" : ""}`}
                onClick={() => handleSelectPerson(person)}
                onMouseEnter={() => setActiveIndex(index)}
              >
                <Avatar person={person} size={26} />
                <span className="person-search-name">{person.name}</span>
                {person.aliases && person.aliases.length > 0 && (
                  <span className="muted tiny" style={{ marginLeft: 4 }}>
                    ({person.aliases.join(", ")})
                  </span>
                )}
                <span className="muted">{person.groups?.[0]?.name ?? ""}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function RelationshipEntryList({
  entries,
  empty = "No recorded relationship",
}: {
  entries: Array<{
    label_en: string;
    label_ur?: string | null;
    relationship_type?: string;
    derived?: boolean;
  }>;
  empty?: string;
}) {
  if (!entries.length) {
    return <div className="empty-inline">{empty}</div>;
  }
  return (
    <div className="relation-list">
      {entries.map((entry, index) => (
        <div className="relation-row" key={`${entry.relationship_type ?? entry.label_en}-${index}`}>
          <span className="relation-en">{entry.label_en}</span>
          {entry.label_ur && (
            <span className="relation-ur" dir="rtl" lang="ur">
              {entry.label_ur}
            </span>
          )}
          {entry.derived && <span className="tag tag-derived">derived</span>}
        </div>
      ))}
    </div>
  );
}

export function RelationChip({ entry }: { entry: { label_en: string; label_ur?: string | null } }) {
  return (
    <span className="chip">
      {entry.label_en}
      {entry.label_ur && (
        <span className="chip-ur" dir="rtl" lang="ur">
          {" "}
          / {entry.label_ur}
        </span>
      )}
    </span>
  );
}
