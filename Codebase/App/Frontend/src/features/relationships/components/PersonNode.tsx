import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { initialsOf } from "../../../markdown";
import type { PersonNodeData } from "../types";

export const PersonNode = memo(function PersonNode({
  data,
  selected,
}: NodeProps) {
  const personData = data as unknown as PersonNodeData;
  const classes = [
    "person-node-card",
    personData.isPerspective ? "is-perspective" : "",
    personData.isFrom ? "is-from" : "",
    personData.isTo ? "is-to" : "",
    personData.isPathIntermediate ? "is-path-intermediate" : "",
    personData.isVirtual ? "is-virtual" : "",
    selected ? "is-selected" : "",
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={classes}>
      <Handle type="target" position={Position.Top} />
      <button
        type="button"
        className="person-node-drag nodrag"
        draggable
        onDragStart={(event) => personData.onDragStart?.(event, personData.id)}
        aria-label={`Drag ${personData.name} to FROM or TO`}
        title="Drag to FROM or TO"
      >
        ⠿
      </button>
      <span className="person-node-avatar" aria-hidden="true">{initialsOf(personData.name)}</span>
      <div className="person-node-copy">
        <div className="person-node-name">
          {personData.name}
          {personData.isPerspective && <span className="node-perspective-mark">•</span>}
        </div>
        {personData.subtitle && (
          <div className="person-node-subtitle">
            <span className="node-sub-en">{personData.subtitle}</span>
            {personData.subtitleUr && <span className="node-sub-ur" dir="rtl" lang="ur"> · {personData.subtitleUr}</span>}
          </div>
        )}
      </div>
      <button
        type="button"
        className="person-node-info nodrag"
        onClick={(event) => {
          event.stopPropagation();
          personData.onInfo?.(personData.id);
        }}
        aria-label={`Information for ${personData.name}`}
        title={`Information for ${personData.name}`}
      >
        ⓘ
      </button>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
});
