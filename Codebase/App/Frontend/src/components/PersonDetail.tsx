import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api";
import { Markdown } from "../markdown";
import type { CompareResult, Journal, Person, PersonProfileData, RelationshipResult } from "../types";
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
  perspectiveId,
  perspectiveName,
  onViewFrom,
  onCompare,
  onEdit,
  onDelete,
  onOpenPerson,
  onShowRelationshipPath,
  onOpenJournal,
}: {
  person: Person;
  perspectiveId?: string | null;
  perspectiveName?: string;
  onViewFrom: (personId: string) => void;
  onCompare?: (personId: string) => void;
  onEdit?: (person: Person) => void;
  onDelete?: (person: Person) => void;
  onOpenPerson?: (personId: string) => void;
  onShowRelationshipPath?: (personId: string) => void;
  onOpenJournal?: (personId: string) => void;
}) {
  const [profileData, setProfileData] = useState<PersonProfileData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [activeTab, setActiveTab] = useState<"overview" | "relationships" | "journal">("overview");

  // Embedded Journal editing state
  const [journalMode, setJournalMode] = useState<"view" | "edit">("view");
  const [journalDraft, setJournalDraft] = useState("");
  const [journalInfo, setJournalInfo] = useState<string | null>(null);
  const [journalError, setJournalError] = useState<unknown>(null);

  const loadProfile = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.people.profile(person.id, perspectiveId || undefined);
      setProfileData(res.profile);
      setJournalDraft(res.profile.journal.content);
    } catch (err: unknown) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [person.id, perspectiveId]);

  useEffect(() => {
    void loadProfile();
  }, [loadProfile]);

  const handleSaveJournal = async () => {
    if (!profileData) return;
    try {
      const updated = await api.journals.save(person.id, journalDraft, {
        modified_ns: profileData.journal.modified_ns,
        sha256: profileData.journal.sha256,
      });
      setProfileData({ ...profileData, journal: updated });
      setJournalDraft(updated.content);
      setJournalMode("view");
      setJournalInfo("Saved to journal.md");
      setJournalError(null);
      setTimeout(() => setJournalInfo(null), 2500);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.code === "JOURNAL_CONFLICT") {
        setJournalError(
          new Error(
            "journal.md was modified on disk by an external editor. Reload to merge changes before saving."
          )
        );
        void loadProfile();
      } else {
        setJournalError(err);
      }
    }
  };

  const handleAppendJournal = async () => {
    const text = window.prompt(`New journal note for ${person.name}:`);
    if (!text || !text.trim()) return;
    try {
      const updated = await api.journals.append(person.id, text.trim());
      if (profileData) {
        setProfileData({ ...profileData, journal: updated });
      }
      setJournalDraft(updated.content);
      setJournalInfo("Entry appended.");
      setJournalError(null);
      setTimeout(() => setJournalInfo(null), 2500);
    } catch (err: unknown) {
      setJournalError(err);
    }
  };

  const facts: Array<[string, string]> = [];
  if (person.birth_year) facts.push(["Born", String(person.birth_year)]);
  if (person.gender) {
    facts.push([
      "Gender",
      { male: "Male", female: "Female", unknown: "Unknown" }[person.gender] ?? person.gender,
    ]);
  }
  if (person.marital_status) facts.push(["Marital status", "Single"]);
  if (person.branch) facts.push(["Branch", person.branch]);
  if (person.folder) facts.push(["Folder", person.folder]);

  const perspectiveRel = profileData?.perspective;
  const primaryRel = perspectiveRel?.primary?.[0];
  const additionalRels = perspectiveRel?.additional || [];

  return (
    <div className="person-profile-container" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* HEADER */}
      <div className="profile-head" style={{ alignItems: "flex-start", gap: 16 }}>
        <Avatar person={person} size={64} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
            <h2 style={{ margin: 0 }}>{person.name}</h2>
            {person.aliases.length > 0 && (
              <span className="muted small">({person.aliases.join(" / ")})</span>
            )}
          </div>

          <div className="group-chips" style={{ marginTop: 6, display: "flex", gap: 6, flexWrap: "wrap" }}>
            {person.groups.map((group) => (
              <span className="chip chip-group" key={group.id}>
                {group.name}
                {group.is_primary ? " · primary" : ""}
              </span>
            ))}
          </div>

          {/* PERSPECTIVE RELATIONSHIP HIGHLIGHT */}
          {perspectiveRel && (
            <div
              className="perspective-highlight-card"
              style={{
                marginTop: 12,
                padding: "10px 14px",
                background: "var(--accent-soft)",
                borderRadius: 8,
                border: "1px solid var(--line-strong)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
                <div>
                  <span className="tiny muted" style={{ textTransform: "uppercase", letterSpacing: 0.5, fontWeight: 600 }}>
                    Relationship to {perspectiveName || "Current Perspective"}
                  </span>
                  <div style={{ fontSize: 16, fontWeight: 700, color: "var(--accent-strong)", marginTop: 2 }}>
                    {primaryRel ? primaryRel.label_en : "No direct kinship derived"}
                    {primaryRel?.label_ur && (
                      <span className="urdu-label" style={{ marginLeft: 8, fontWeight: 400, opacity: 0.85 }}>
                        ({primaryRel.label_ur})
                      </span>
                    )}
                  </div>
                  {additionalRels.length > 0 && (
                    <div className="tiny muted" style={{ marginTop: 4 }}>
                      <strong>Additional paths:</strong>{" "}
                      {additionalRels.map((r) => r.label_en + (r.label_ur ? ` (${r.label_ur})` : "")).join(" · ")}
                    </div>
                  )}
                </div>

                {onShowRelationshipPath && primaryRel && (
                  <button
                    type="button"
                    className="btn btn-outline"
                    style={{ fontSize: 12, padding: "5px 12px", background: "#fff" }}
                    onClick={() => onShowRelationshipPath(person.id)}
                    title="View relationship connection on the diagram"
                  >
                    Show Relationship Path →
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ACTION BAR */}
      <div className="profile-actions" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <Button kind="primary" onClick={() => onViewFrom(person.id)}>
          View from this person
        </Button>
        {onEdit && (
          <Button onClick={() => onEdit(person)}>
            Edit Person
          </Button>
        )}
        {onCompare && (
          <Button onClick={() => onCompare(person.id)}>
            Compare
          </Button>
        )}
        {onDelete && (
          <Button kind="danger" onClick={() => onDelete(person)}>
            Remove Person
          </Button>
        )}
      </div>

      {/* NAVIGATION TABS */}
      <div className="tabs" style={{ margin: "4px 0" }}>
        <button
          type="button"
          className={`tab profile-tab ${activeTab === "overview" ? "active" : ""}`}
          onClick={() => setActiveTab("overview")}
        >
          Overview &amp; Facts
        </button>
        <button
          type="button"
          className={`tab profile-tab ${activeTab === "relationships" ? "active" : ""}`}
          onClick={() => setActiveTab("relationships")}
        >
          Relationships
        </button>
        <button
          type="button"
          className={`tab profile-tab ${activeTab === "journal" ? "active" : ""}`}
          onClick={() => setActiveTab("journal")}
        >
          Journal {profileData?.journal?.content?.trim() ? "✓" : ""}
        </button>
      </div>

      <ErrorNote error={error} />

      {loading && !profileData && (
        <div className="muted" style={{ padding: "24px 0", textAlign: "center" }}>
          Loading profile details…
        </div>
      )}

      {profileData && (
        <div className="profile-tab-content" style={{ minHeight: 220 }}>
          {/* TAB 1: OVERVIEW */}
          {activeTab === "overview" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div className="fact-grid">
                {facts.map(([label, value]) => (
                  <div className="fact" key={label}>
                    <span className="muted small">{label}</span>
                    <span style={{ wordBreak: "break-all" }}>{value}</span>
                  </div>
                ))}
              </div>

              {person.note_en && (
                <div className="diff-card" style={{ background: "#fafbfc" }}>
                  <span className="muted small" style={{ fontWeight: 600 }}>Note (English):</span>
                  <p style={{ margin: "4px 0 0" }}>{person.note_en}</p>
                </div>
              )}

              {person.note_ur && (
                <div className="diff-card" style={{ background: "#fafbfc" }}>
                  <span className="muted small" style={{ fontWeight: 600 }}>Note (Urdu):</span>
                  <p style={{ margin: "4px 0 0", fontFamily: "'Noto Naskh Arabic', serif", fontSize: 16 }}>
                    {person.note_ur}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* TAB 2: RELATIONSHIPS */}
          {activeTab === "relationships" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {/* FAMILY RELATIONSHIPS */}
              <div>
                <h4 style={{ margin: "0 0 8px", color: "var(--ink)", borderBottom: "1px solid var(--line)", paddingBottom: 4 }}>
                  Family Relationships (Direct facts)
                </h4>

                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 10 }}>
                  {/* Parents */}
                  <div className="diff-card" style={{ margin: 0 }}>
                    <span className="small muted" style={{ fontWeight: 600 }}>Parents</span>
                    {profileData.family.parents.length === 0 ? (
                      <div className="tiny muted" style={{ marginTop: 4 }}>No parent facts recorded</div>
                    ) : (
                      <ul style={{ margin: "6px 0 0", paddingLeft: 16 }}>
                        {profileData.family.parents.map((parent) => (
                          <li key={parent.id} style={{ marginBottom: 4 }}>
                            <button
                              type="button"
                              className="btn-link"
                              style={{ border: "none", background: "none", padding: 0, cursor: "pointer", color: "var(--accent)", fontWeight: 600 }}
                              onClick={() => onOpenPerson?.(parent.id)}
                            >
                              {parent.name}
                            </button>{" "}
                            <span className="tiny muted">({parent.role}, {parent.kind})</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>

                  {/* Spouses */}
                  <div className="diff-card" style={{ margin: 0 }}>
                    <span className="small muted" style={{ fontWeight: 600 }}>Spouse(s)</span>
                    {profileData.family.spouses.length === 0 ? (
                      <div className="tiny muted" style={{ marginTop: 4 }}>No marriage facts recorded</div>
                    ) : (
                      <ul style={{ margin: "6px 0 0", paddingLeft: 16 }}>
                        {profileData.family.spouses.map((spouse) => (
                          <li key={spouse.id} style={{ marginBottom: 4 }}>
                            <button
                              type="button"
                              className="btn-link"
                              style={{ border: "none", background: "none", padding: 0, cursor: "pointer", color: "var(--accent)", fontWeight: 600 }}
                              onClick={() => onOpenPerson?.(spouse.id)}
                            >
                              {spouse.name}
                            </button>{" "}
                            <span className="tiny muted">
                              ({spouse.status}{spouse.year ? `, ${spouse.year}` : ""})
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>

                  {/* Children */}
                  <div className="diff-card" style={{ margin: 0 }}>
                    <span className="small muted" style={{ fontWeight: 600 }}>Children</span>
                    {profileData.family.children.length === 0 ? (
                      <div className="tiny muted" style={{ marginTop: 4 }}>No children recorded</div>
                    ) : (
                      <ul style={{ margin: "6px 0 0", paddingLeft: 16 }}>
                        {profileData.family.children.map((child) => (
                          <li key={child.id} style={{ marginBottom: 4 }}>
                            <button
                              type="button"
                              className="btn-link"
                              style={{ border: "none", background: "none", padding: 0, cursor: "pointer", color: "var(--accent)", fontWeight: 600 }}
                              onClick={() => onOpenPerson?.(child.id)}
                            >
                              {child.name}
                            </button>{" "}
                            <span className="tiny muted">({child.kind})</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>

                  {/* Siblings */}
                  <div className="diff-card" style={{ margin: 0 }}>
                    <span className="small muted" style={{ fontWeight: 600 }}>Siblings</span>
                    {profileData.family.siblings.length === 0 ? (
                      <div className="tiny muted" style={{ marginTop: 4 }}>No sibling facts recorded</div>
                    ) : (
                      <ul style={{ margin: "6px 0 0", paddingLeft: 16 }}>
                        {profileData.family.siblings.map((sibling) => (
                          <li key={sibling.id} style={{ marginBottom: 4 }}>
                            <button
                              type="button"
                              className="btn-link"
                              style={{ border: "none", background: "none", padding: 0, cursor: "pointer", color: "var(--accent)", fontWeight: 600 }}
                              onClick={() => onOpenPerson?.(sibling.id)}
                            >
                              {sibling.name}
                            </button>{" "}
                            <span className="tiny muted">
                              {sibling.gender === "female" ? "Sister" : sibling.gender === "male" ? "Brother" : "Sibling"}
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              </div>

              {/* GENERAL RELATIONSHIPS */}
              <div>
                <h4 style={{ margin: "0 0 8px", color: "var(--ink)", borderBottom: "1px solid var(--line)", paddingBottom: 4 }}>
                  General Relationships (Friends, Colleagues, Mentors)
                </h4>

                {profileData.general.length === 0 ? (
                  <div className="empty-state" style={{ padding: "16px", background: "#fafbfc", borderRadius: 8 }}>
                    No non-family general relationships recorded for {person.name}.
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {profileData.general.map((rel) => (
                      <div
                        key={rel.id}
                        className="diff-card"
                        style={{ margin: 0, display: "flex", justifyContent: "space-between", alignItems: "center" }}
                      >
                        <div>
                          <button
                            type="button"
                            className="btn-link"
                            style={{ border: "none", background: "none", padding: 0, cursor: "pointer", color: "var(--accent)", fontWeight: 600, fontSize: 14 }}
                            onClick={() => onOpenPerson?.(rel.other_person.id)}
                          >
                            {rel.other_person.name}
                          </button>
                          <span className="chip" style={{ marginLeft: 8, fontSize: 11 }}>
                            {rel.label}
                          </span>
                          {rel.notes && (
                            <p className="tiny muted" style={{ margin: "4px 0 0" }}>
                              {rel.notes}
                            </p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 3: JOURNAL */}
          {activeTab === "journal" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div className="journal-toolbar" style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                {journalMode === "view" ? (
                  <>
                    <Button onClick={() => setJournalMode("edit")}>Edit Journal</Button>
                    <Button onClick={() => void handleAppendJournal()}>Append Note</Button>
                  </>
                ) : (
                  <>
                    <Button kind="primary" onClick={() => void handleSaveJournal()}>
                      Save to journal.md
                    </Button>
                    <Button onClick={() => setJournalMode("view")}>Cancel</Button>
                  </>
                )}
                <Button onClick={() => void loadProfile()} title="Reload from disk">
                  Reload from disk
                </Button>
                <span className="muted tiny journal-path" style={{ marginLeft: "auto" }}>
                  {profileData.journal.path}
                </span>
              </div>

              {journalError ? <ErrorNote error={journalError} /> : null}
              {journalInfo && <div className="info-note">{journalInfo}</div>}

              {journalMode === "edit" ? (
                <textarea
                  className="journal-editor"
                  style={{ minHeight: 240, width: "100%", padding: 12, borderRadius: 8, border: "1px solid var(--line-strong)" }}
                  value={journalDraft}
                  onChange={(e) => setJournalDraft(e.target.value)}
                  spellCheck={false}
                  placeholder="Write Markdown notes about this person..."
                />
              ) : profileData.journal.content.trim() ? (
                <div className="journal-view" style={{ padding: "12px 16px", background: "#fafbfc", borderRadius: 8, border: "1px solid var(--line)" }}>
                  <Markdown text={profileData.journal.content} />
                </div>
              ) : (
                <div className="empty-state" style={{ padding: 24, textAlign: "center" }}>
                  <p className="muted" style={{ margin: "0 0 12px" }}>
                    No journal prose recorded yet for {person.name}.
                  </p>
                  <Button kind="primary" onClick={() => setJournalMode("edit")}>
                    Write First Entry
                  </Button>
                </div>
              )}

              <div className="muted tiny journal-hint">
                Canonical source: <code>journal.md</code>. Edits in external editors (VS Code, Obsidian, Notepad) are preserved upon reloading.
              </div>
            </div>
          )}
        </div>
      )}
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
              "Reload to see the new content, then merge manually and save again."
          )
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
