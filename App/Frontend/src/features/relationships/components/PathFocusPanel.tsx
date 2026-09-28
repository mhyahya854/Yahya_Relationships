import type { RelationshipEntry, RelationshipPath } from "../types";

export function PathFocusPanel({
  entry,
  path,
  perspectiveName,
  target,
  totalForLabel,
  activeIndex = 0,
  onSelectPath,
  onExit,
}: {
  entry: RelationshipEntry;
  path: RelationshipPath;
  perspectiveName: string;
  target: { id: string; name: string };
  totalForLabel: number;
  activeIndex?: number;
  onSelectPath: (index: number) => void;
  onExit: () => void;
}) {
  const ancestors = path.common_ancestors ?? [];
  return (
    <div className="path-focus-panel">
      <div className="path-focus-head">
        <div className="rel-section-title">
          Path Proof {totalForLabel > 1 ? `(${activeIndex + 1} of ${totalForLabel})` : ""}
        </div>
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
        {path.explanation ? (
          <p>{path.explanation}</p>
        ) : path.domain === "general" ? (
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
        <div className="path-alternatives" style={{ marginTop: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
            <span className="muted small font-medium">
              Path {activeIndex + 1} of {totalForLabel}
            </span>
            <div style={{ display: "flex", gap: 4 }}>
              <button
                type="button"
                className="btn btn-ghost"
                disabled={activeIndex <= 0}
                onClick={() => onSelectPath(activeIndex - 1)}
                title="Previous Path"
              >
                ← Prev
              </button>
              <button
                type="button"
                className="btn btn-ghost"
                disabled={activeIndex >= totalForLabel - 1}
                onClick={() => onSelectPath(activeIndex + 1)}
                title="Next Path"
              >
                Next →
              </button>
            </div>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {Array.from({ length: totalForLabel }, (_, index) => index).map(
              (index) => (
                <button
                  type="button"
                  key={index}
                  className={`btn ${index === activeIndex ? "btn-primary" : "btn-ghost"}`}
                  onClick={() => onSelectPath(index)}
                >
                  Path {index + 1}
                </button>
              ),
            )}
          </div>
        </div>
      )}
    </div>
  );
}
