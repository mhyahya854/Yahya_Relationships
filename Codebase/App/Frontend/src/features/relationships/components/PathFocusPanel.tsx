import type { RelationshipEntry, RelationshipPath } from "../types";

export function PathFocusPanel({
  entry,
  path,
  perspectiveName,
  target,
  totalForLabel,
  onSelectPath,
  onExit,
}: {
  entry: RelationshipEntry;
  path: RelationshipPath;
  perspectiveName: string;
  target: { id: string; name: string };
  totalForLabel: number;
  onSelectPath: (index: number) => void;
  onExit: () => void;
}) {
  const ancestors = path.common_ancestors ?? [];
  return (
    <div className="path-focus-panel">
      <div className="path-focus-head">
        <div className="rel-section-title">Path focus</div>
        <button type="button" className="btn btn-ghost" onClick={onExit}>
          Exit path (Esc)
        </button>
      </div>
      <h3>{entry.label_en}</h3>
      {entry.label_ur && (
        <div className="relation-ur" dir="rtl" lang="ur">
          {entry.label_ur}
        </div>
      )}
      <dl className="path-facts">
        {path.domain === "family" && path.side && (
          <>
            <dt>Side</dt>
            <dd>{path.side}</dd>
          </>
        )}
        {path.degree != null && (
          <>
            <dt>Degree</dt>
            <dd>{path.degree}</dd>
          </>
        )}
        {path.removal != null && (
          <>
            <dt>Removal</dt>
            <dd>{path.removal}</dd>
          </>
        )}
        <dt>Path length</dt>
        <dd>{path.distance} steps</dd>
        {ancestors.length > 0 && (
          <>
            <dt>Common ancestor{ancestors.length > 1 ? "s" : ""}</dt>
            <dd>
              {ancestors
                .map(
                  (ancestor) =>
                    ancestor.name + (ancestor.is_virtual ? " (shared family)" : ""),
                )
                .join(", ")}
            </dd>
          </>
        )}
      </dl>
      <div className="path-explanation">
        {path.domain === "general" ? (
          <p>
            {target.name} is directly connected to {perspectiveName} by the
            recorded relationship “{entry.label_en}”. No family derivation is
            involved.
          </p>
        ) : path.derived ? (
          <p>
            This {path.side ? `${path.side} side ` : "family "}path runs over{" "}
            {path.distance} recorded family steps
            {ancestors.length
              ? ` through shared ancestor${ancestors.length > 1 ? "s" : ""} ${ancestors
                  .map((item) => item.name)
                  .join(", ")}`
              : ""}
            , which makes {target.name} a {entry.label_en} of {perspectiveName}.
          </p>
        ) : (
          <p>
            {target.name} is directly recorded as {entry.label_en} of{" "}
            {perspectiveName}.
          </p>
        )}
      </div>
      {totalForLabel > 1 && (
        <div className="path-alternatives">
          <div className="muted small">
            {totalForLabel} valid path{totalForLabel > 1 ? "s" : ""} for this
            relationship:
          </div>
          {Array.from({ length: Math.min(totalForLabel, 5) }, (_, index) => index).map(
            (index) => (
              <button
                type="button"
                key={index}
                className="btn btn-ghost"
                onClick={() => onSelectPath(index)}
              >
                Path {index + 1}
              </button>
            ),
          )}
        </div>
      )}
    </div>
  );
}
