import type { ExpansionFilter } from "../types";

const FILTER_LABELS: Record<ExpansionFilter, string> = {
  parents: "Parents",
  children: "Children",
  siblings: "Siblings",
  spouses: "Spouses",
  general: "General",
};

export function ExpandControls({
  personName,
  active,
  onToggle,
  filters,
}: {
  personName: string;
  active: Set<ExpansionFilter>;
  onToggle: (filter: ExpansionFilter) => void;
  filters?: ExpansionFilter[];
}) {
  const visibleFilters = filters ?? (Object.keys(FILTER_LABELS) as ExpansionFilter[]);
  return (
    <div className="expand-bar" aria-label={`Relationship filters for ${personName}`}>
      <span className="expand-label">
        Show relationships:
      </span>
      {visibleFilters.map((filter) => {
        const isActive = active.has(filter);
        return (
          <button
            type="button"
            key={filter}
            className={`expand-chip ${isActive ? "active" : ""}`}
            onClick={() => onToggle(filter)}
            title={isActive ? `Collapse ${FILTER_LABELS[filter]}` : `Expand ${FILTER_LABELS[filter]}`}
          >
            {FILTER_LABELS[filter]}
          </button>
        );
      })}
    </div>
  );
}
