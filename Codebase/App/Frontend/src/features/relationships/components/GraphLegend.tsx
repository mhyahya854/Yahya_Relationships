import { GRAPH_LEGEND } from "../graph/edgeStyles";

export function GraphLegend() {
  return (
    <div className="graph-legend">
      {GRAPH_LEGEND.map((item) => (
        <span className="legend-item" key={item.label}>
          <span
            className={`legend-line legend-style-${item.style}`}
            style={{ borderTopColor: item.color }}
          />
          {item.label}
        </span>
      ))}
    </div>
  );
}
