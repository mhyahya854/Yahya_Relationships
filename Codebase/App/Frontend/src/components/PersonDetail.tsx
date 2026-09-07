import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { CompareResult, Person, PersonProfileData, RelationshipResult } from "../types";
import { JournalEditor } from "../features/journals/JournalEditor";
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

  const [journalDirty, setJournalDirty] = useState(false);
  const [pendingTab, setPendingTab] = useState<"overview" | "relationships" | null>(null);

  const loadProfile = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.people.profile(person.id, perspectiveId || undefined);
      setProfileData(res.profile);
    } catch (err: unknown) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [person.id, perspectiveId]);

  useEffect(() => {
    void loadProfile();
  }, [loadProfile]);

  const selectTab = (next: "overview" | "relationships" | "journal") => {
    if (activeTab === "journal" && next !== "journal" && journalDirty) {
      setPendingTab(next);
      return;
    }
    setActiveTab(next);
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
          onClick={() => selectTab("overview")}
        >
          Overview &amp; Facts
        </button>
        <button
          type="button"
          className={`tab profile-tab ${activeTab === "relationships" ? "active" : ""}`}
          onClick={() => selectTab("relationships")}
        >
          Relationships
        </button>
        <button
          type="button"
          className={`tab profile-tab ${activeTab === "journal" ? "active" : ""}`}
          onClick={() => selectTab("journal")}
        >
          Journal {profileData?.journal ? (profileData.journal.exists === false ? "⚠" : (profileData.journal.content?.trim() ? "✓" : "")) : ""}
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
            <JournalEditor
              person={person}
              initialJournal={profileData.journal}
              onDirtyChange={setJournalDirty}
            />
          )}
        </div>
      )}
      {pendingTab && (
        <div className="journal-inline-dialog" role="alertdialog" aria-modal="true" aria-label="Unsaved Journal changes">
          <h3>Unsaved Journal changes</h3>
          <p>Switching tabs will discard the current Journal draft.</p>
          <div className="journal-dialog-actions">
            <Button kind="primary" onClick={() => setPendingTab(null)}>Keep Editing</Button>
            <Button
              kind="danger"
              onClick={() => {
                setJournalDirty(false);
                setActiveTab(pendingTab);
                setPendingTab(null);
              }}
            >
              Discard
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export function useRelationship(
  perspectiveId: string | null,
  targetId: string | null,
  refreshKey?: number | string,
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
  }, [perspectiveId, targetId, refreshKey]);

  return { result, error, loading };
}

export function JournalModal({
  person,
  onClose,
}: {
  person: Person;
  onClose: () => void;
}) {
  const [dirty, setDirty] = useState(false);
  const [closeGuardOpen, setCloseGuardOpen] = useState(false);
  const requestClose = () => {
    if (dirty) setCloseGuardOpen(true);
    else onClose();
  };

  return (
    <Modal title={`Journal — ${person.name}`} onClose={requestClose} wide closeOnEscape>
      <JournalEditor person={person} onDirtyChange={setDirty} />
      {closeGuardOpen && (
        <div className="journal-inline-dialog" role="alertdialog" aria-modal="true" aria-label="Unsaved Journal changes">
          <h3>Unsaved Journal changes</h3>
          <p>Closing now will discard the current Journal draft.</p>
          <div className="journal-dialog-actions">
            <Button kind="primary" onClick={() => setCloseGuardOpen(false)}>Keep Editing</Button>
            <Button kind="danger" onClick={onClose}>Discard</Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
