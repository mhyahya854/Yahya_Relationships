import { Modal } from "../../../components/ui";
import type { BackupInfo } from "../../../types";

export function BackupDetailsDialog({
  backup,
  onClose,
}: {
  backup: BackupInfo & {
    timestamp?: string;
    app_version?: string;
    schema_version?: number;
    file_count?: number;
    total_size_bytes?: number;
    person_count?: number;
    journal_count?: number;
    verified?: boolean;
    integrity_status?: string;
  };
  onClose: () => void;
}) {
  return (
    <Modal title={`Backup Details: ${backup.label || backup.name}`} onClose={onClose} wide>
      <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
        <div
          style={{
            padding: "10px 14px",
            borderRadius: "8px",
            background: backup.verified !== false ? "var(--ok-soft, #eef9f5)" : "var(--warn-soft, #fff8ec)",
            border: `1px solid ${backup.verified !== false ? "#b7eb8f" : "#ffe58f"}`,
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <div>
            <strong>Verification Status: {backup.verified !== false ? "VERIFIED ✓" : "CORRUPTED ⚠"}</strong>
            <div className="muted small">{backup.path}</div>
          </div>
          <span className="chip">{backup.integrity_status || "ok"}</span>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
          <div style={{ background: "#f8fafc", padding: "12px", borderRadius: "8px", border: "1px solid #e2e8f0" }}>
            <h4 style={{ margin: "0 0 8px 0" }}>Metadata</h4>
            <div className="small muted">Backup ID: <code>{backup.name}</code></div>
            <div className="small muted">Created: <strong>{backup.created || backup.timestamp || "Unknown"}</strong></div>
            <div className="small muted">App Version: <strong>{backup.app_version || "1.0.0"}</strong></div>
            <div className="small muted">Schema Version: <strong>{backup.schema_version ?? 1}</strong></div>
          </div>

          <div style={{ background: "#f8fafc", padding: "12px", borderRadius: "8px", border: "1px solid #e2e8f0" }}>
            <h4 style={{ margin: "0 0 8px 0" }}>Content Summary</h4>
            <div className="small muted">People Count: <strong>{backup.person_count ?? "N/A"}</strong></div>
            <div className="small muted">Journal Count: <strong>{backup.journal_count ?? "N/A"}</strong></div>
            <div className="small muted">Total Files: <strong>{backup.files ?? backup.file_count ?? "N/A"}</strong></div>
            <div className="small muted">Total Size: <strong>{backup.total_size_bytes ? `${(backup.total_size_bytes / 1024).toFixed(1)} KB` : "N/A"}</strong></div>
          </div>
        </div>
      </div>
    </Modal>
  );
}
