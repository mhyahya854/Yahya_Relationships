import { Button, Icon } from "../../../components/ui";
import { GraphLegend } from "./GraphLegend";

export function GraphDock({
  personName,
  zoomPercent,
  immersive,
  onZoomOut,
  onZoomIn,
  onFit,
  onToggleFullscreen,
  includeGeneral = true,
}: {
  personName: string;
  zoomPercent: number;
  immersive: boolean;
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
          <Icon name="zoom-out" />
        </Button>
        <output className="graph-zoom-value" aria-live="polite">{zoomPercent}%</output>
        <Button className="graph-dock-button" onClick={onZoomIn} ariaLabel="Zoom in" title="Zoom in">
          <Icon name="zoom-in" />
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
      <details className="graph-legend-popover">
        <summary className="graph-dock-button" aria-label="Show relationship legend" title="Relationship legend">
          <Icon name="legend" />
        </summary>
        <GraphLegend includeGeneral={includeGeneral} />
      </details>
    </div>
  );
}
