import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { CompareResult, Person, PersonProfileData, RelationshipResult } from "../types";
import { JournalEditor } from "../features/journals/JournalEditor";
import {
  Avatar,
  Button,
  ErrorNote,
  Icon,
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
  onViewFamily,
  onOpenJournal,
  onJournalDirtyChange,
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
  onViewFamily?: (personId: string) => void;
  onOpenJournal?: (personId: string) => void;
  onJournalDirtyChange?: (dirty: boolean) => void;
}) {
  const [profileData, setProfileData] = useState<PersonProfileData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [activeTab, setActiveTab] = useState<"overview" | "relationships" | "journal">("overview");

  const [journalDirty, setJournalDirty] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [pendingTab, setPendingTab] = useState<"overview" | "relationships" | null>(null);

  const reportJournalDirty = useCallback((dirty: boolean) => {
    setJournalDirty(dirty);
    onJournalDirtyChange?.(dirty);
  }, [onJournalDirtyChange]);

  useEffect(() => {
    reportJournalDirty(false);
    setPendingTab(null);
  }, [person.id, reportJournalDirty]);

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
    setMoreOpen(false);
    setActiveTab(next);
  };

  const facts: Array<[string, string]> = [["Name", person.name]];
  if (person.aliases.length) facts.push(["Nickname / Alias", person.aliases.join(" · ")]);
  if (person.birth_year) facts.push(["Born", String(person.birth_year)]);
  if (person.gender) {
    facts.push([
      "Gender",
      { male: "Male", female: "Female", unknown: "Unknown" }[person.gender] ?? person.gender,
    ]);
  }
  if (person.groups.length) facts.push(["Groups", person.groups.map((group) => group.name).join(" · ")]);
  if (person.marital_status) facts.push(["Marital status", person.marital_status.replace(/_/g, " ")]);
  if (person.branch) facts.push(["Branch", person.branch]);

  const perspectiveRel = profileData?.perspective;
  const primaryRel = perspectiveRel?.primary?.[0];
  const additionalRels = perspectiveRel?.additional || [];

  return (
    <div className="person-profile-container">
      <div className="profile-identity">
        <Avatar person={person} size={82} />
        <div className="profile-identity-copy">
          <h2>{person.name}</h2>
          {person.aliases.length > 0 && (
            <div className="profile-alias" dir="auto">{person.aliases.join(" · ")}</div>
          )}
          <div className="group-chips">
            {person.groups.map((group) => (
              <span className="chip chip-group" key={group.id}>
                {group.name}
              </span>
            ))}
            {person.groups.some((group) => group.is_primary) && <span className="chip chip-primary">Primary</span>}
          </div>
        </div>
      </div>

      {perspectiveRel && (
        <section className="profile-relationship" aria-label="Relationship summary">
          <div className="profile-relationship-icon"><Icon name="family" size={24} /></div>
          <div className="profile-relationship-copy">
            <div className="profile-relationship-value">
              {primaryRel ? primaryRel.label_en : "No direct kinship derived"}
              {primaryRel?.label_ur && <span dir="rtl" lang="ur"> · {primaryRel.label_ur}</span>}
            </div>
            <div className="profile-relationship-context">
              From the perspective of {perspectiveName || "the current person"}
            </div>
            {additionalRels.length > 0 && (
              <div className="tiny muted">
                Additional paths: {additionalRels.map((r) => r.label_en + (r.label_ur ? ` (${r.label_ur})` : "")).join(" · ")}
              </div>
            )}
          </div>
          {onShowRelationshipPath && primaryRel && (
            <Button
              className="profile-path-button"
              disabled={journalDirty}
              onClick={() => onShowRelationshipPath(person.id)}
              title="View relationship connection on the diagram"
            >
              Show Relationship Path <Icon name="path" />
            </Button>
          )}
        </section>
      )}

      <div className="profile-actions">
        <Button kind="primary" onClick={() => onViewFrom(person.id)}>
          <Icon name="view" /> View from this person
        </Button>
        {onViewFamily && (
          <Button disabled={journalDirty} onClick={() => onViewFamily(person.id)}>
            <Icon name="family" /> View Family Tree<span className="sr-only"> View Family</span>
          </Button>
        )}
        {onEdit && (
          <Button onClick={() => onEdit(person)}>
            <Icon name="edit" /> Edit Person
          </Button>
        )}
        {onCompare && (
          <Button onClick={() => onCompare(person.id)}>
            <Icon name="compare" /> Compare
          </Button>
        )}
        {onDelete && (
          <details className="profile-more" open={moreOpen} onToggle={(event) => setMoreOpen(event.currentTarget.open)}>
            <summary className="btn" aria-label="More profile actions" title="More profile actions"><Icon name="more" /></summary>
            <div className="profile-more-menu">
              <Button kind="danger" onClick={() => { setMoreOpen(false); onDelete(person); }}>Remove Person</Button>
            </div>
          </details>
        )}
      </div>

      <div className="tabs profile-tabs">
        <button
          type="button"
          className={`tab profile-tab ${activeTab === "overview" ? "active" : ""}`}
          onClick={() => selectTab("overview")}
        >
          Overview
        </button>
        <button
          type="button"
          className={`tab profile-tab ${activeTab === "relationships" ? "active" : ""}`}
          onClick={() => selectTab("relationships")}
        >
          Connections<span className="sr-only"> Relationships</span>
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
            <div className="profile-overview">
              <section className="profile-section profile-details-section">
                <div className="profile-section-head">
                  <h3>Details</h3>
                  {onEdit && <Button kind="ghost" onClick={() => onEdit(person)}><Icon name="edit" /> Edit</Button>}
                </div>
                <div className="fact-grid">
                  {facts.map(([label, value]) => (
                    <div className="fact" key={label}>
                      <span className="muted small">{label}</span>
                      <span dir="auto">{value}</span>
                    </div>
                  ))}
                </div>
                {person.folder && (
                  <details className="technical-disclosure">
                    <summary>Technical Details</summary>
                    <div className="technical-details"><strong>Canonical folder</strong><br />{person.folder}</div>
                  </details>
                )}
              </section>

              <section className="profile-section profile-about-section">
                <div className="profile-section-head"><h3>About</h3></div>
                {person.note_en && <p dir="auto">{person.note_en}</p>}
                {person.note_ur && <p className="urdu-note" dir="rtl" lang="ur">{person.note_ur}</p>}
                {!person.note_en && !person.note_ur && <div className="empty-inline">No notes recorded yet.</div>}
              </section>
            </div>
          )}

          {/* TAB 2: RELATIONSHIPS */}
          {activeTab === "relationships" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {/* FAMILY RELATIONSHIPS */}
              <div>
                <h4 style={{ margin: "0 0 8px", color: "var(--ink)", borderBottom: "1px solid var(--line)", paddingBottom: 4 }}>
                  Family Connections <span className="sr-only">Relationships</span>
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
                  Friends, Colleagues &amp; Mentors
                </h4>

                {profileData.general.length === 0 ? (
                  <div className="empty-state" style={{ padding: "16px", background: "var(--surface-secondary)", borderRadius: 8 }}>
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
              onDirtyChange={reportJournalDirty}
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
                reportJournalDirty(false);
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
