import { useEffect, useMemo, useState } from "react";
import { api } from "../../../api";
import { Avatar, Button, ErrorNote } from "../../../components/ui";
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

/**
 * One compact target group in the builder. Paths are queried at the safe
 * canonical maximum as soon as a person is added to TO; checking a route is a
 * display filter only and never writes relationship data.
 */
export function RelationshipTargetCard({
  person,
  perspectiveId,
  perspectiveName,
  active,
  refreshVersion,
  clearPathsVersion,
  onActivate,
  onRemove,
  onOpenInfo,
  onHighlightedPathsChange,
}: {
  person: Person;
  perspectiveId: string;
  perspectiveName: string;
  active: boolean;
  refreshVersion: number;
  clearPathsVersion: number;
  onActivate: () => void;
  onRemove: () => void;
  onOpenInfo: () => void;
  onHighlightedPathsChange: (personId: string, paths: RelationshipPath[]) => void;
}) {
  const [result, setResult] = useState<RelationshipResultDto | null>(null);
  const [paths, setPaths] = useState<RelationshipPath[]>([]);
  const [selectedPathIds, setSelectedPathIds] = useState<string[]>([]);
  const [pathsTruncated, setPathsTruncated] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setPaths([]);
    setSelectedPathIds([]);
    setPathsTruncated(false);
    onHighlightedPathsChange(person.id, []);
    void Promise.all([
      api.relationships.get(perspectiveId, person.id),
      relationshipsApi.paths(perspectiveId, person.id, 30, 50),
    ])
      .then(([relationship, pathResponse]) => {
        if (cancelled) return;
        setResult(relationship);
        setPaths(pathResponse.paths);
        setSelectedPathIds(pathResponse.paths.map((path) => path.id));
        setPathsTruncated(pathResponse.truncated);
      })
      .catch((nextError: unknown) => {
        if (!cancelled) setError(nextError);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [onHighlightedPathsChange, person.id, perspectiveId, refreshVersion]);

  useEffect(() => {
    if (clearPathsVersion !== 0) setSelectedPathIds([]);
  }, [clearPathsVersion]);

  const highlightedPaths = useMemo(
    () => paths.filter((path) => selectedPathIds.includes(path.id)),
    [paths, selectedPathIds],
  );

  useEffect(() => {
    onHighlightedPathsChange(person.id, highlightedPaths);
  }, [highlightedPaths, onHighlightedPathsChange, person.id]);

  const entries = result ? [...result.primary, ...result.additional] : [];
  const primary = entries[0] ?? null;

  return (
    <section
      className={`relationship-target-card ${active ? "is-active" : ""}`}
      onFocusCapture={onActivate}
      onMouseDown={onActivate}
      aria-label={`Relationship paths to ${person.name}`}
    >
      <header className="target-card-heading">
        <Avatar person={person} size={34} />
        <div className="target-card-title">
          <strong>{person.name}</strong>
          <span>{primary ? primary.label_en : loading ? "Finding recorded routes…" : "No direct label stored"}</span>
        </div>
        <button
          type="button"
          className="builder-info-button"
          onClick={onOpenInfo}
          aria-label={`Information for ${person.name}`}
          title={`Information for ${person.name}`}
        >
          ⓘ
        </button>
        <Button kind="ghost" className="icon-button target-card-remove" onClick={onRemove} ariaLabel={`Remove ${person.name} from TO`} title={`Remove ${person.name} from TO`}>×</Button>
      </header>
      <div className="target-card-body">
        <ErrorNote error={error} />
        <div className="target-path-summary">
          <strong>All valid paths</strong>
          <span>{paths.length} route{paths.length === 1 ? "" : "s"} from {perspectiveName}</span>
        </div>
        {pathsTruncated && <p className="target-path-truncated">The safe 50-route response limit was reached; no route was silently stored or inferred.</p>}
        {!loading && !error && paths.length === 0 && <p className="empty-inline">No supported route was returned.</p>}
        <div className="target-path-list" aria-label={`Canonical paths between ${perspectiveName} and ${person.name}`}>
          {paths.map((path, index) => {
            const checked = selectedPathIds.includes(path.id);
            const tone = pathTone(path);
            return (
              <label className={`target-path-option tone-${tone} ${checked ? "is-selected" : ""}`} key={path.id}>
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(event) => {
                    const nextChecked = event.currentTarget.checked;
                    setSelectedPathIds((current) => nextChecked
                      ? [...current, path.id]
                      : current.filter((id) => id !== path.id));
                  }}
                />
                <span className="path-check" aria-hidden="true">✓</span>
                <span className="target-path-copy">
                  <strong>{index + 1}. {path.label_en}</strong>
                  {path.label_ur && <span dir="rtl" lang="ur">{path.label_ur}</span>}
                  <small>{path.distance} step{path.distance === 1 ? "" : "s"}{path.side ? ` · ${path.side}` : path.domain === "connection" ? " · recorded route only" : ""}</small>
                </span>
              </label>
            );
          })}
        </div>
        {entries.length > 0 && (
          <details className="target-card-evidence">
            <summary>Relationship interpretation</summary>
            <div>
              {entries.map((entry, index) => (
                <p key={entryKey(entry, index)}><strong>{entry.label_en}</strong>{entry.derived ? " · canonical family derivation" : " · recorded fact"}</p>
              ))}
            </div>
          </details>
        )}
      </div>
    </section>
  );
}
