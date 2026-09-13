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
  className = "",
  ariaLabel,
  ariaExpanded,
  ariaPressed,
}: {
  children: ReactNode;
  onClick?: () => void;
  kind?: "default" | "primary" | "danger" | "ghost";
  disabled?: boolean;
  title?: string;
  type?: "button" | "submit";
  className?: string;
  ariaLabel?: string;
  ariaExpanded?: boolean;
  ariaPressed?: boolean;
}) {
  return (
    <button
      type={type}
      className={`btn btn-${kind} ${className}`.trim()}
      onClick={onClick}
      disabled={disabled}
      title={title}
      aria-label={ariaLabel}
      aria-expanded={ariaExpanded}
      aria-pressed={ariaPressed}
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
      {person.photo_path ? (
        <img className="avatar-image" src={person.photo_path} alt="" />
      ) : (
        initialsOf(person.name)
      )}
    </span>
  );
}

export type IconName =
  | "add"
  | "back"
  | "backup"
  | "close"
  | "compare"
  | "edit"
  | "family"
  | "fit"
  | "folder"
  | "fullscreen"
  | "journal"
  | "legend"
  | "more"
  | "path"
  | "profile"
  | "reload"
  | "search"
  | "target"
  | "view"
  | "zoom-in"
  | "zoom-out";

export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, ReactNode> = {
    add: <path d="M12 5v14M5 12h14" />,
    back: <path d="m15 18-6-6 6-6" />,
    backup: <><ellipse cx="12" cy="5" rx="7" ry="3" /><path d="M5 5v7c0 1.7 3.1 3 7 3s7-1.3 7-3V5M5 12v7c0 1.7 3.1 3 7 3s7-1.3 7-3v-7" /></>,
    close: <path d="m6 6 12 12M18 6 6 18" />,
    compare: <><circle cx="9" cy="12" r="5" /><circle cx="15" cy="12" r="5" /></>,
    edit: <><path d="m4 20 4.2-1 10-10a2.1 2.1 0 0 0-3-3l-10 10L4 20Z" /><path d="m13.8 7.2 3 3" /></>,
    family: <><circle cx="12" cy="5" r="2.5" /><circle cx="5" cy="18" r="2.5" /><circle cx="19" cy="18" r="2.5" /><path d="M12 7.5v4M5 15.5v-4h14v4" /></>,
    fit: <path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5" />,
    folder: <path d="M3 6.5A2.5 2.5 0 0 1 5.5 4H10l2 2h6.5A2.5 2.5 0 0 1 21 8.5v8A2.5 2.5 0 0 1 18.5 19h-13A2.5 2.5 0 0 1 3 16.5v-10Z" />,
    fullscreen: <path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5M9 9 3 3m12 6 6-6M9 15l-6 6m12-6 6 6" />,
    journal: <><path d="M6 3h11a2 2 0 0 1 2 2v16H8a3 3 0 0 1-3-3V4a1 1 0 0 1 1-1Z" /><path d="M8 7h7M8 11h7M8 15h4" /></>,
    legend: <><path d="M4 7h4M11 7h9M4 12h4M11 12h9M4 17h4M11 17h9" /></>,
    more: <><circle cx="5" cy="12" r="1" fill="currentColor" /><circle cx="12" cy="12" r="1" fill="currentColor" /><circle cx="19" cy="12" r="1" fill="currentColor" /></>,
    path: <><circle cx="5" cy="17" r="2" /><circle cx="19" cy="7" r="2" /><path d="M7 17c5 0 5-10 10-10" /></>,
    profile: <><circle cx="12" cy="8" r="4" /><path d="M5 21c.7-4.2 3-6.3 7-6.3s6.3 2.1 7 6.3" /></>,
    reload: <><path d="M20 11a8 8 0 1 0-2.3 5.7" /><path d="M20 4v7h-7" /></>,
    search: <><circle cx="10.5" cy="10.5" r="6" /><path d="m15 15 4 4" /></>,
    target: <><circle cx="12" cy="12" r="7" /><circle cx="12" cy="12" r="2" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" /></>,
    view: <><path d="M2.5 12s3.2-5.5 9.5-5.5 9.5 5.5 9.5 5.5-3.2 5.5-9.5 5.5S2.5 12 2.5 12Z" /><circle cx="12" cy="12" r="2.5" /></>,
    "zoom-in": <><circle cx="10.5" cy="10.5" r="6" /><path d="m15 15 4 4M10.5 7.5v6M7.5 10.5h6" /></>,
    "zoom-out": <><circle cx="10.5" cy="10.5" r="6" /><path d="m15 15 4 4M7.5 10.5h6" /></>,
  };
  return (
    <svg className="ui-icon" width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      {paths[name]}
    </svg>
  );
}

export function Modal({
  title,
  children,
  onClose,
  wide,
  closeOnEscape = false,
  className = "",
}: {
  title: ReactNode;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
  closeOnEscape?: boolean;
  className?: string;
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
        className={`modal ${wide ? "modal-wide" : ""} ${className}`.trim()}
        onMouseDown={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === "string" ? title : "Dialog"}
      >
        <div className="modal-head">
          <h2>{title}</h2>
          <Button kind="ghost" className="icon-button" onClick={onClose} title="Close" ariaLabel="Close dialog">
            <Icon name="close" /><span className="sr-only">✕</span>
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
  onOpenChange,
}: {
  people: Person[];
  onSelect: (person: Person) => void;
  placeholder?: string;
  autoFocus?: boolean;
  inputRef?: RefCallback<HTMLInputElement>;
  ariaLabel?: string;
  disabled?: boolean;
  onOpenChange?: (open: boolean) => void;
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
        onOpenChange?.(false);
        setActiveIndex(-1);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [onOpenChange]);

  const handleSelectPerson = (person: Person) => {
    onSelect(person);
    setQuery("");
    setOpen(false);
    onOpenChange?.(false);
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
          onOpenChange?.(true);
          setActiveIndex(-1);
        }}
        onFocus={() => {
          setOpen(true);
          onOpenChange?.(true);
        }}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setOpen(true);
            onOpenChange?.(true);
            setActiveIndex((prev) =>
              matches.length === 0 ? -1 : prev + 1 < matches.length ? prev + 1 : 0,
            );
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setOpen(true);
            onOpenChange?.(true);
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
            onOpenChange?.(false);
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
