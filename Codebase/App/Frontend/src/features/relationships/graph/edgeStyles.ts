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
      stroke: "#34778a",
      strokeWidth: 1.7,
      strokeDasharray: "7 5",
    };
  }
  switch (edge.type) {
    case "parent_child":
      if (edge.subtype === "biological") {
        return {
          className: "rf-edge-parent",
          stroke: "#536b61",
          strokeWidth: 2.2,
        };
      }
      return {
        className: "rf-edge-parent-alt",
        stroke: "#956821",
        strokeWidth: 2,
        strokeDasharray: "2 5",
      };
    case "marriage":
      return {
        className: "rf-edge-marriage",
        stroke: "#8a718d",
        strokeWidth: 1.8,
      };
    case "sibling_group":
      return {
        className: "rf-edge-sibling",
        stroke: "#7b817c",
        strokeWidth: 1.5,
        strokeDasharray: "4 4",
      };
    default:
      return {
        className: "rf-edge-default",
        stroke: "#9a9f99",
        strokeWidth: 1.4,
        strokeDasharray: "2 4",
      };
  }
}

export const GRAPH_LEGEND = [
  { label: "Parent / child (biological)", style: "solid", color: "#536b61" },
  { label: "Parent / child (adopted/step/foster…)", style: "dashed", color: "#956821" },
  { label: "Marriage", style: "solid", color: "#8a718d" },
  { label: "Sibling", style: "dotted", color: "#7b817c" },
  { label: "General relationship", style: "dashed", color: "#34778a" },
];
