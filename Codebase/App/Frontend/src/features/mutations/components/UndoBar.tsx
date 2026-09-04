import React from "react";

interface Props {
  description: string;
  onUndo: () => void;
  onDismiss: () => void;
  loading?: boolean;
}

export const UndoBar: React.FC<Props> = ({
  description,
  onUndo,
  onDismiss,
  loading = false,
}) => {
  return (
    <div className="undo-bar">
      <span>{description}</span>
      <button className="undo-bar-btn" onClick={onUndo} disabled={loading}>
        {loading ? "Undoing..." : "Undo"}
      </button>
      <button className="undo-bar-close" onClick={onDismiss} title="Dismiss">
        &times;
      </button>
    </div>
  );
};
