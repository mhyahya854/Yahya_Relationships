import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { PersonNodeData } from "../types";

export const PersonNode = memo(function PersonNode({
  data,
  selected,
}: NodeProps) {
  const personData = data as unknown as PersonNodeData;
  const classes = [
    "person-node-card",
    personData.isPerspective ? "is-perspective" : "",
    personData.isVirtual ? "is-virtual" : "",
    selected ? "is-selected" : "",
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={classes}>
      <Handle type="target" position={Position.Top} />
      <div className="person-node-name">
        {personData.name}
        {personData.isPerspective && (
          <span className="node-perspective-mark">★</span>
        )}
      </div>
      {personData.subtitle && (
        <div className="person-node-subtitle">
          <span className="node-sub-en">{personData.subtitle}</span>
          {personData.subtitleUr && (
            <span className="node-sub-ur" dir="rtl" lang="ur">
              {personData.subtitleUr}
            </span>
          )}
        </div>
      )}
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
});
