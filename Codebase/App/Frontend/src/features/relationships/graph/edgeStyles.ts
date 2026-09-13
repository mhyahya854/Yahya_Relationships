import type { GraphEdgeDto } from "../types";

export interface EdgeVisual {
  className: string;
  stroke: string;
  strokeWidth: number;
  strokeDasharray?: string;
}

export function edgeVisual(edge: GraphEdgeDto): EdgeVisual {
  if (edge.domain === "general") {
    return {
      className: "rf-edge-general",
      stroke: "var(--general-line)",
      strokeWidth: 1.7,
      strokeDasharray: "7 5",
    };
  }
  switch (edge.type) {
    case "parent_child":
      if (edge.subtype === "biological") {
        return {
          className: "rf-edge-parent",
          stroke: "var(--family-line)",
          strokeWidth: 2.2,
        };
      }
      return {
        className: "rf-edge-parent-alt",
        stroke: "var(--family-alt-line)",
        strokeWidth: 2,
        strokeDasharray: "2 5",
      };
    case "marriage":
      return {
        className: "rf-edge-marriage",
        stroke: "var(--marriage-line)",
        strokeWidth: 1.8,
      };
    case "sibling_group":
      return {
        className: "rf-edge-sibling",
        stroke: "var(--sibling-line)",
        strokeWidth: 1.5,
        strokeDasharray: "4 4",
      };
    default:
      return {
        className: "rf-edge-default",
        stroke: "var(--relationship-line)",
        strokeWidth: 1.4,
        strokeDasharray: "2 4",
      };
  }
}

export const GRAPH_LEGEND = [
  { label: "Parent / child (biological)", style: "solid", color: "var(--family-line)" },
  { label: "Parent / child (adopted/step/foster…)", style: "dashed", color: "var(--family-alt-line)" },
  { label: "Marriage", style: "solid", color: "var(--marriage-line)" },
  { label: "Sibling", style: "dotted", color: "var(--sibling-line)" },
  { label: "General relationship", style: "dashed", color: "var(--general-line)" },
];
