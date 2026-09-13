import { Button, Icon } from "../../../components/ui";
import type { ExpansionFilter } from "../types";
import { ExpandControls } from "./ExpandControls";
import { GraphLegend } from "./GraphLegend";

export function GraphDock({
  personName,
  active,
  filters,
  zoomPercent,
  immersive,
  onToggle,
  onZoomOut,
  onZoomIn,
  onFit,
  onToggleFullscreen,
  includeGeneral = true,
}: {
  personName: string;
  active: Set<ExpansionFilter>;
  filters?: ExpansionFilter[];
  zoomPercent: number;
  immersive: boolean;
  onToggle: (filter: ExpansionFilter) => void;
  onZoomOut: () => void;
  onZoomIn: () => void;
  onFit: () => void;
  onToggleFullscreen: () => void;
  includeGeneral?: boolean;
}) {
  return (
    <div className="relationships-footer glass-panel" aria-label="Graph controls and relationship legend">
      <div className="graph-zoom-controls" aria-label="Graph zoom controls">
        <Button className="graph-dock-button" onClick={onZoomOut} ariaLabel="Zoom out" title="Zoom out">
          <span className="graph-zoom-glyph" aria-hidden="true">−</span>
        </Button>
        <output className="graph-zoom-value" aria-live="polite">{zoomPercent}%</output>
        <Button className="graph-dock-button" onClick={onZoomIn} ariaLabel="Zoom in" title="Zoom in">
          <span className="graph-zoom-glyph" aria-hidden="true">+</span>
        </Button>
      </div>
      <Button className="graph-dock-button" onClick={onFit} ariaLabel="Fit graph to viewport" title="Fit graph to viewport">
        <Icon name="fit" />
      </Button>
      <Button
        className="graph-dock-button"
        onClick={onToggleFullscreen}
        ariaLabel={immersive ? "Exit graph fullscreen" : "Enter graph fullscreen"}
        ariaPressed={immersive}
        title={immersive ? "Exit fullscreen" : "Enter fullscreen"}
      >
        <Icon name="fullscreen" />
      </Button>
      <span className="graph-dock-divider" aria-hidden="true" />
      <ExpandControls personName={personName} active={active} filters={filters} onToggle={onToggle} />
      <span className="graph-dock-divider" aria-hidden="true" />
      <GraphLegend includeGeneral={includeGeneral} />
    </div>
  );
}
