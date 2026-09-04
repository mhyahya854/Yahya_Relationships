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
      stroke: "#2f7d8f",
      strokeWidth: 1.7,
      strokeDasharray: "7 5",
    };
  }
  switch (edge.type) {
    case "parent_child":
      if (edge.subtype === "biological") {
        return {
          className: "rf-edge-parent",
          stroke: "#40536f",
          strokeWidth: 2.2,
        };
      }
      return {
        className: "rf-edge-parent-alt",
        stroke: "#8a6412",
        strokeWidth: 2,
        strokeDasharray: "2 5",
      };
    case "marriage":
      return {
        className: "rf-edge-marriage",
        stroke: "#6b4f8f",
        strokeWidth: 1.8,
      };
    case "sibling_group":
      return {
        className: "rf-edge-sibling",
        stroke: "#7d8b9d",
        strokeWidth: 1.5,
        strokeDasharray: "4 4",
      };
    default:
      return {
        className: "rf-edge-default",
        stroke: "#9aa3af",
        strokeWidth: 1.4,
        strokeDasharray: "2 4",
      };
  }
}

export const GRAPH_LEGEND = [
  { label: "Parent / child (biological)", style: "solid", color: "#40536f" },
  { label: "Parent / child (adopted/step/foster…)", style: "dashed", color: "#8a6412" },
  { label: "Marriage", style: "solid", color: "#6b4f8f" },
  { label: "Sibling", style: "dotted", color: "#7d8b9d" },
  { label: "General relationship", style: "dashed", color: "#2f7d8f" },
];
