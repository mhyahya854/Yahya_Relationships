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
}: {
  title: ReactNode;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div
        className={`modal ${wide ? "modal-wide" : ""}`}
        onMouseDown={(event) => event.stopPropagation()}
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
}: {
  people: Person[];
  onSelect: (person: Person) => void;
  placeholder?: string;
  autoFocus?: boolean;
  inputRef?: RefCallback<HTMLInputElement>;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  const matches = (query.trim()
    ? people.filter((person) => {
        const haystack = [person.name, ...person.aliases]
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
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  return (
    <div className="person-search" ref={boxRef}>
      <input
        ref={inputRef}
        value={query}
        autoFocus={autoFocus}
        placeholder={placeholder ?? "Search people…"}
        onChange={(event) => {
          setQuery(event.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && matches.length === 1) {
            onSelect(matches[0]);
            setOpen(false);
            setQuery(matches[0].name);
          }
          if (event.key === "Escape") setOpen(false);
        }}
      />
      {open && (
        <div className="person-search-results">
          {matches.length === 0 && (
            <div className="person-search-empty">No matches</div>
          )}
          {matches.map((person) => (
            <button
              type="button"
              key={person.id}
              className="person-search-row"
              onClick={() => {
                onSelect(person);
                setQuery(person.name);
                setOpen(false);
              }}
            >
              <Avatar person={person} size={26} />
              <span className="person-search-name">{person.name}</span>
              <span className="muted">{person.groups[0]?.name ?? ""}</span>
            </button>
          ))}
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
