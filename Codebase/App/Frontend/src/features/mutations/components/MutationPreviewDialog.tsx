import React from "react";
import type { MutationPreviewResult } from "../../../types";

interface Props {
  preview: MutationPreviewResult;
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
}

export const MutationPreviewDialog: React.FC<Props> = ({
  preview,
  onConfirm,
  onCancel,
  loading = false,
}) => {
  return (
    <div className="modal-backdrop mutation-preview-dialog">
      <div className="modal-card">
        <div className="modal-header">
          <h3>
            {preview.valid ? (
              <span style={{ color: "var(--ok)" }}>Consequence Preview</span>
            ) : (
              <span style={{ color: "var(--danger)" }}>Invalid Mutation</span>
            )}
          </h3>
          <button className="btn-close" onClick={onCancel}>
            &times;
          </button>
        </div>

        <div className="modal-body">
          {!preview.valid && (
            <div className="diff-invalid">
              <strong>Validation Blocked:</strong> {preview.message}
              {preview.code && <div className="small muted">Error code: {preview.code}</div>}
            </div>
          )}

          {preview.direct_changes.length > 0 && (
            <div className="preview-direct">
              <h4>Direct Fact Change</h4>
              <ul>
                {preview.direct_changes.map((change, i) => (
                  <li key={i}>{change}</li>
                ))}
              </ul>
            </div>
          )}

          {preview.warnings.length > 0 && (
            <div className="diff-card diff-warning">
              <strong>Warnings:</strong>
              <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                {preview.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          {preview.valid && (
            <div className="preview-section">
              <h4 style={{ margin: 0, fontSize: 14 }}>Derived Kinship Consequences:</h4>

              {preview.derived_added.length === 0 && preview.derived_removed.length === 0 && (
                <div className="muted small">No other derived kinship paths are affected by this change.</div>
              )}

              {preview.derived_added.length > 0 && (
                <div className="diff-card diff-added">
                  <strong>+ {preview.derived_added.length} Derived Relationship{preview.derived_added.length > 1 ? "s" : ""} Added:</strong>
                  <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                    {preview.derived_added.map((item, i) => (
                      <li key={i} style={{ marginBottom: 4 }}>
                        <strong>{item.person_b_name}</strong> becomes <strong>{item.label_en}</strong>
                        {item.side ? ` (${item.side})` : ""} to {item.person_a_name}
                        {item.nodes && item.nodes.length > 2 && (
                          <div className="muted tiny" style={{ marginTop: 2 }}>
                            via {item.nodes.map((n) => n.name).join(" → ")}
                          </div>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {preview.derived_removed.length > 0 && (
                <div className="diff-card diff-removed">
                  <strong>&minus; {preview.derived_removed.length} Derived Relationship{preview.derived_removed.length > 1 ? "s" : ""} Removed:</strong>
                  <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                    {preview.derived_removed.map((item, i) => (
                      <li key={i} style={{ marginBottom: 4 }}>
                        <strong>{item.person_b_name}</strong> is no longer <strong>{item.label_en}</strong>
                        {item.side ? ` (${item.side})` : ""} to {item.person_a_name}
                        {item.nodes && item.nodes.length > 2 && (
                          <div className="muted tiny" style={{ marginTop: 2 }}>
                            via {item.nodes.map((n) => n.name).join(" → ")}
                          </div>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button className="btn btn-outline" onClick={onCancel} disabled={loading}>
            Cancel
          </button>
          {preview.valid && (
            <button className="btn btn-primary" onClick={onConfirm} disabled={loading}>
              {loading ? "Saving..." : "Confirm & Save Fact"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
