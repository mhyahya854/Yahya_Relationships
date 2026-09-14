import { useEffect, useMemo, useState } from "react";
import { api } from "../../../api";
import { Avatar, Button, ErrorNote, Icon } from "../../../components/ui";
import type { Person } from "../../../types";
import { relationshipsApi } from "../api";
import type { RelationshipEntry, RelationshipPath, RelationshipResultDto } from "../types";

function entryKey(entry: RelationshipEntry, index: number): string {
  return entry.id ?? `${entry.domain}:${entry.semantic_id ?? entry.relationship_type}:${index}`;
}

function pathTone(path: RelationshipPath): string {
  if (path.domain !== "family") return "neutral";
  if (path.side === "maternal") return "maternal";
  if (path.side === "paternal") return "paternal";
  return "neutral";
}

export function RelationshipTargetCard({
  person,
  perspectiveId,
  perspectiveName,
  active,
  refreshVersion,
  revealPathsVersion,
  clearPathsVersion,
  onActivate,
  onRemove,
  onMakeCentral,
  onHighlightedPathsChange,
  onNavigateToProfile,
  onOpenJournal,
  onNavigateToFamily,
  onAddRelationship,
  onEditRelationship,
  onCompare,
  onEditPerson,
  onDeletePerson,
}: {
  person: Person;
  perspectiveId: string;
  perspectiveName: string;
  active: boolean;
  refreshVersion: number;
  revealPathsVersion: number;
  clearPathsVersion: number;
  onActivate: () => void;
  onRemove: () => void;
  onMakeCentral: () => void;
  onHighlightedPathsChange: (personId: string, paths: RelationshipPath[]) => void;
  onNavigateToProfile?: (personId: string) => void;
  onOpenJournal: (person: Person) => void;
  onNavigateToFamily?: (personId: string) => void;
  onAddRelationship: () => void;
  onEditRelationship: (entry: RelationshipEntry) => void;
  onCompare: () => void;
  onEditPerson: () => void;
  onDeletePerson: () => void;
}) {
  const [result, setResult] = useState<RelationshipResultDto | null>(null);
  const [paths, setPaths] = useState<RelationshipPath[]>([]);
  const [selectedPathIds, setSelectedPathIds] = useState<string[]>([]);
  const [showAll, setShowAll] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [pathsLoading, setPathsLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    setCollapsed(!active);
  }, [active]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api.relationships
      .get(perspectiveId, person.id)
      .then((payload) => {
        if (!cancelled) setResult(payload);
      })
      .catch((nextError: unknown) => {
        if (!cancelled) setError(nextError);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [person.id, perspectiveId, refreshVersion]);

  useEffect(() => {
    setShowAll(false);
    setPaths([]);
    setSelectedPathIds([]);
    onHighlightedPathsChange(person.id, []);
  }, [person.id, perspectiveId]);

  useEffect(() => {
    if (clearPathsVersion === 0) return;
    setSelectedPathIds([]);
  }, [clearPathsVersion]);

  const highlightedPaths = useMemo(
    () => paths.filter((path) => selectedPathIds.includes(path.id)),
    [paths, selectedPathIds],
  );

  useEffect(() => {
    onHighlightedPathsChange(person.id, highlightedPaths);
  }, [highlightedPaths, onHighlightedPathsChange, person.id]);

  const loadPaths = async () => {
    if (paths.length) return paths;
    setPathsLoading(true);
    setError(null);
    try {
      const response = await relationshipsApi.paths(perspectiveId, person.id);
      setPaths(response.paths);
      return response.paths;
    } catch (nextError) {
      setError(nextError);
      return [];
    } finally {
      setPathsLoading(false);
    }
  };

  const setAllPathsVisible = async (next: boolean) => {
    onActivate();
    setShowAll(next);
    if (!next) {
      setSelectedPathIds([]);
      return;
    }
    const available = await loadPaths();
    if (!selectedPathIds.length && available[0]) {
      setSelectedPathIds([available[0].id]);
    }
  };

  useEffect(() => {
    if (!active || revealPathsVersion === 0) return;
    void setAllPathsVisible(true);
    // revealPathsVersion is an explicit command token.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [revealPathsVersion]);

  const entries = result ? [...result.primary, ...result.additional] : [];
  const primary = entries[0] ?? null;
  const otherCount = Math.max(0, entries.length - 1);

  return (
    <section
      className={`relationship-target-card ${active ? "is-active" : ""}`}
      onFocusCapture={onActivate}
      onMouseDown={onActivate}
      aria-label={`Relationship to ${person.name}`}
    >
      <div className="target-card-heading">
        <Avatar person={person} size={48} />
        <div className="target-card-title">
          <strong>{person.name}</strong>
          {primary ? (
            <span className="target-card-primary-role">
              {primary.label_en}
              {primary.label_ur && <span dir="rtl" lang="ur"> · {primary.label_ur}</span>}
            </span>
          ) : (
            <span className="muted small">{loading ? "Calculating relationship…" : "No recorded relationship"}</span>
          )}
        </div>
        <Button
          kind="ghost"
          className="icon-button target-card-collapse"
          onClick={() => setCollapsed((value) => !value)}
          ariaLabel={collapsed ? `Expand ${person.name}` : `Collapse ${person.name}`}
          ariaExpanded={!collapsed}
          title={collapsed ? "Expand target" : "Collapse target"}
        >
          <span className="target-card-disclosure" aria-hidden="true"><Icon name="chevron-down" size={16} /></span>
        </Button>
        <Button
          kind="ghost"
          className="icon-button target-card-remove"
          onClick={onRemove}
          ariaLabel={`Remove ${person.name} from Relationship Explorer`}
          title="Remove target"
        >
          <Icon name="close" />
        </Button>
      </div>

      {!collapsed && (
        <div className="target-card-body">
          <ErrorNote error={error} />
          {primary && (
            <div className="target-card-summary">
              <span className={`family-badge ${primary.side === "maternal" ? "badge-maternal" : primary.side === "paternal" ? "badge-paternal" : "badge-derived"}`}>
                Main relationship
              </span>
              <strong>{primary.label_en}</strong>
              {primary.label_ur && <span dir="rtl" lang="ur">{primary.label_ur}</span>}
              {otherCount > 0 && <span className="muted small">+{otherCount} other relationship{otherCount === 1 ? "" : "s"}</span>}
            </div>
          )}

          <label className="relationship-path-toggle">
            <span>
              <strong>Show all relationship paths</strong>
              <small>Derived evidence only · no facts are changed</small>
            </span>
            <input
              type="checkbox"
              checked={showAll}
              onChange={(event) => void setAllPathsVisible(event.currentTarget.checked)}
            />
            <span className="toggle-track" aria-hidden="true"><span /></span>
          </label>

          {showAll && (
            <div className="target-path-list" aria-label={`Canonical paths between ${perspectiveName} and ${person.name}`}>
              {pathsLoading && <div className="muted small">Loading canonical paths…</div>}
              {!pathsLoading && paths.length === 0 && <div className="empty-inline">No supported relationship paths were returned.</div>}
              {paths.map((path, index) => {
                const checked = selectedPathIds.includes(path.id);
                const tone = pathTone(path);
                return (
                  <label className={`target-path-option tone-${tone} ${checked ? "is-selected" : ""}`} key={path.id}>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(event) => {
                        onActivate();
                        const nextChecked = event.currentTarget.checked;
                        setSelectedPathIds((current) => nextChecked
                          ? [...current, path.id]
                          : current.filter((id) => id !== path.id));
                      }}
                    />
                    <span className="path-check" aria-hidden="true">✓</span>
                    <span className="target-path-copy">
                      <strong>{path.label_en}</strong>
                      {path.label_ur && <span dir="rtl" lang="ur">{path.label_ur}</span>}
                      <small>Path {index + 1} · {path.distance} step{path.distance === 1 ? "" : "s"}{path.side ? ` · ${path.side}` : ""}</small>
                    </span>
                  </label>
                );
              })}
            </div>
          )}

          <div className="inspector-primary-actions target-card-actions">
            {onNavigateToProfile && <Button onClick={() => onNavigateToProfile(person.id)}><Icon name="profile" /><span>View Profile</span><span className="inspector-chevron"><Icon name="chevron-right" size={16} /></span></Button>}
            <Button onClick={() => onOpenJournal(person)}><Icon name="journal" /><span>Journal</span><span className="inspector-chevron"><Icon name="chevron-right" size={16} /></span></Button>
            {onNavigateToFamily && <Button onClick={() => onNavigateToFamily(person.id)}><Icon name="family" /><span>View Family Tree</span><span className="inspector-chevron"><Icon name="chevron-right" size={16} /></span></Button>}
            <Button onClick={onMakeCentral}><Icon name="target" /><span>Make central person</span><span className="inspector-chevron"><Icon name="chevron-right" size={16} /></span></Button>
          </div>

          <div className="inspector-metadata target-card-metadata">
            <div className="inspector-meta-row"><Icon name="profile" /><div><span>Full name</span><strong>{person.name}</strong></div></div>
            <div className="inspector-meta-row"><Icon name="family" /><div><span>Relationship to {perspectiveName}</span><strong>{primary?.label_en ?? "Not recorded"}</strong></div></div>
            <div className="inspector-meta-row"><Icon name="journal" /><div><span>Person details</span><strong>{person.birth_year ? `Born ${person.birth_year}` : "Birth year unknown"}{person.gender ? ` · ${person.gender}` : ""}</strong></div></div>
          </div>

          {entries.length > 0 && (
            <details className="inspector-disclosure inspector-evidence">
              <summary><Icon name="path" /> Relationship evidence</summary>
              <div className="inspector-disclosure-body target-entry-list">
                {entries.map((entry, index) => (
                  <div className="target-entry-row" key={entryKey(entry, index)}>
                    <div>
                      <strong>{entry.label_en}</strong>
                      {entry.label_ur && <span dir="rtl" lang="ur">{entry.label_ur}</span>}
                      <small>{entry.derived ? "Derived from canonical family facts" : "Directly stored fact"}</small>
                    </div>
                    {!entry.derived && <Button kind="ghost" onClick={() => onEditRelationship(entry)}>Edit</Button>}
                  </div>
                ))}
              </div>
            </details>
          )}

          <details className="inspector-disclosure inspector-manage">
            <summary><Icon name="more" /> More actions</summary>
            <div className="inspector-disclosure-body inspector-manage-grid">
              <Button kind="primary" onClick={onAddRelationship}><Icon name="add" /> Add Relationship</Button>
              <Button onClick={onCompare}><Icon name="compare" /> Compare</Button>
              <Button onClick={onEditPerson}><Icon name="edit" /> Edit Person</Button>
              <Button kind="danger" onClick={onDeletePerson}>Delete Person</Button>
            </div>
          </details>
        </div>
      )}
    </section>
  );
}
