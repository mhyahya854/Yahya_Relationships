import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import { Markdown } from "../markdown";
import type { CompareResult, Journal, Person, RelationshipResult } from "../types";
import {
  Avatar,
  Button,
  ErrorNote,
  Modal,
  RelationshipEntryList,
} from "./ui";

export function RelationshipPanel({
  result,
  onViewFrom,
}: {
  result: RelationshipResult;
  onViewFrom?: (personId: string) => void;
}) {
  const target = result.target;
  return (
    <div className="relationship-panel">
      <div className="relationship-subheading">
        How is <strong>{target.name}</strong> related to{" "}
        <strong>{result.perspective.name}</strong>?
      </div>
      <div className="rel-section">
        <div className="rel-section-title">Primary</div>
        <RelationshipEntryList entries={result.primary} />
      </div>
      {result.additional.length > 0 && (
        <div className="rel-section">
          <div className="rel-section-title">Additional paths</div>
          <RelationshipEntryList entries={result.additional} />
        </div>
      )}
      {onViewFrom && (
        <div className="relationship-actions">
          <Button kind="primary" onClick={() => onViewFrom(target.id)}>
            View from this person
          </Button>
        </div>
      )}
    </div>
  );
}

export function CompareModal({
  a,
  b,
  onClose,
  onViewFrom,
}: {
  a: string;
  b: string;
  onClose: () => void;
  onViewFrom: (personId: string) => void;
}) {
  const [result, setResult] = useState<CompareResult | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    api.relationships
      .compare(a, b)
      .then(setResult)
      .catch(setError);
  }, [a, b]);

  return (
    <Modal title="Compare two people" onClose={onClose} wide>
      <ErrorNote error={error} />
      {result && (
        <>
          <div className="compare-grid">
            <div className="compare-col">
              <h3>
                How is {result.b.name} related to {result.a.name}?
              </h3>
              <RelationshipPanel result={result.a_to_b} />
            </div>
            <div className="compare-col">
              <h3>
                How is {result.a.name} related to {result.b.name}?
              </h3>
              <RelationshipPanel result={result.b_to_a} />
            </div>
          </div>
          <div className="compare-actions">
            <span className="muted small">Use this comparison as perspective:</span>
            <Button onClick={() => onViewFrom(result.a.id)}>View as {result.a.name}</Button>
            <Button onClick={() => onViewFrom(result.b.id)}>View as {result.b.name}</Button>
          </div>
        </>
      )}
    </Modal>
  );
}

export function PersonProfile({
  person,
  onViewFrom,
  onCompare,
  onOpenJournal,
}: {
  person: Person;
  onViewFrom: (personId: string) => void;
  onCompare?: (personId: string) => void;
  onOpenJournal: (personId: string) => void;
}) {
  const facts: Array<[string, string]> = [];
  if (person.birth_year) facts.push(["Born", String(person.birth_year)]);
  if (person.gender) {
    facts.push([
      "Gender",
      { male: "Male", female: "Female", unknown: "Unknown" }[person.gender] ??
        person.gender,
    ]);
  }
  if (person.marital_status) facts.push(["Marital status", "Single"]);
  return (
    <div className="person-profile">
      <div className="profile-head">
        <Avatar person={person} size={64} />
        <div>
          <h2>{person.name}</h2>
          {person.aliases.length > 0 && (
            <div className="muted">Alias: {person.aliases.join(" / ")}</div>
          )}
          <div className="group-chips">
            {person.groups.map((group) => (
              <span className="chip chip-group" key={group.id}>
                {group.name}
                {group.is_primary ? " · folder" : ""}
              </span>
            ))}
          </div>
        </div>
      </div>
      {facts.length > 0 && (
        <div className="fact-grid">
          {facts.map(([label, value]) => (
            <div className="fact" key={label}>
              <span className="muted small">{label}</span>
              <span>{value}</span>
            </div>
          ))}
        </div>
      )}
      {person.note_en && (
        <p className="note-en">
          <span className="muted small">Note</span> {person.note_en}
        </p>
      )}
      <div className="profile-actions">
        <Button kind="primary" onClick={() => onViewFrom(person.id)}>
          View from this person
        </Button>
        {onCompare && (
          <Button onClick={() => onCompare(person.id)}>Compare</Button>
        )}
        <Button onClick={() => onOpenJournal(person.id)}>Journal</Button>
      </div>
    </div>
  );
}

export function useRelationship(
  perspectiveId: string | null,
  targetId: string | null,
) {
  const [result, setResult] = useState<RelationshipResult | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!perspectiveId || !targetId) {
      setResult(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    api.relationships
      .get(perspectiveId, targetId)
      .then((payload) => {
        if (!cancelled) setResult(payload);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [perspectiveId, targetId]);

  return { result, error, loading };
}

export function JournalModal({
  person,
  onClose,
}: {
  person: Person;
  onClose: () => void;
}) {
  const [journal, setJournal] = useState<Journal | null>(null);
  const [mode, setMode] = useState<"view" | "edit">("view");
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [info, setInfo] = useState<string | null>(null);

  async function load() {
    try {
      const result = await api.journals.get(person.id);
      setJournal(result);
      setDraft(result.content);
      setError(null);
    } catch (err) {
      setError(err);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [person.id]);

  async function appendEntry() {
    const text = window.prompt("New journal entry for " + person.name);
    if (!text || !text.trim()) return;
    try {
      const result = await api.journals.append(person.id, text.trim());
      setJournal(result);
      setDraft(result.content);
      setInfo("Entry appended.");
      setError(null);
      setTimeout(() => setInfo(null), 2500);
    } catch (err) {
      setError(err);
    }
  }

  async function save() {
    try {
      const result = await api.journals.save(person.id, draft, {
        modified_ns: journal?.modified_ns,
        sha256: journal?.sha256,
      });
      setJournal(result);
      setDraft(result.content);
      setMode("view");
      setInfo("Saved to journal.md");
      setError(null);
      setTimeout(() => setInfo(null), 2500);
    } catch (err) {
      if (err instanceof ApiError && err.code === "JOURNAL_CONFLICT") {
        setError(
          new Error(
            "journal.md changed on disk since it was opened (external edit). " +
              "Reload to see the new content, then merge manually and save again.",
          ),
        );
        await load();
      } else {
        setError(err);
      }
    }
  }

  return (
    <Modal title={`Journal — ${person.name}`} onClose={onClose} wide>
      <div className="journal-toolbar">
        {mode === "view" ? (
          <>
            <Button onClick={() => setMode("edit")}>Edit</Button>
            <Button onClick={() => void appendEntry()}>Append entry</Button>
          </>
        ) : (
          <>
            <Button kind="primary" onClick={() => void save()}>
              Save
            </Button>
            <Button onClick={() => setMode("view")}>Cancel</Button>
          </>
        )}
        <Button onClick={() => void load()} title="Reload journal.md from disk">
          Reload from disk
        </Button>
        <span className="muted tiny journal-path">{journal?.path ?? "…"}</span>
      </div>
      {error ? <ErrorNote error={error} /> : null}
      {info && <div className="info-note">{info}</div>}
      {journal &&
        (mode === "edit" ? (
          <textarea
            className="journal-editor"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            spellCheck={false}
          />
        ) : (
          <div className="journal-view">
            <Markdown text={journal.content} />
          </div>
        ))}
      <div className="muted tiny journal-hint">
        journal.md is the source of truth. Edits made in VS Code, Obsidian or
        Notepad become visible after “Reload from disk”; the app never silently
        overwrites an external change.
      </div>
    </Modal>
  );
}
