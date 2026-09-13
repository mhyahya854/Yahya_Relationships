import { useState } from "react";
import { Button, Modal } from "../../../components/ui";
import { dataRootApi } from "../api";
import type { DataRootHealth } from "../types";

export function DataRootHealthDialog({
  health,
  onClose,
  onRefresh,
}: {
  health: DataRootHealth;
  onClose: () => void;
  onRefresh: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [repairResult, setRepairResult] = useState<string | null>(null);
  const canRepair = health.issues.some((issue) =>
    ["MISSING_PERSON_FOLDER", "MISSING_JOURNAL", "ARCHIVED_ACTIVE_MISMATCH"].includes(issue.code),
  );
  const hasIssues = health.issues.length > 0;

  async function handleRepair() {
    setBusy(true);
    setRepairResult(null);
    try {
      const res = await dataRootApi.repair();
      if (res.ok) {
        setRepairResult(`Repaired ${res.repaired} non-destructive item(s).`);
        onRefresh();
      } else {
        setRepairResult(`Repair attempted: ${(res.errors ?? ["No repair details returned."]).join(", ")}`);
      }
    } catch (err) {
      setRepairResult(err instanceof Error ? err.message : "Repair failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Data Root Health Audit" onClose={onClose} wide>
      <div className="health-audit-content" style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
        <div
          className="health-status-badge"
          style={{
            padding: "10px 14px",
            borderRadius: "8px",
            background: !hasIssues ? "var(--ok-soft)" : "var(--warn-soft)",
            border: `1px solid ${!hasIssues ? "var(--ok)" : "var(--warn)"}`,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div>
            <strong>Status: {!hasIssues ? "HEALTHY ✓" : "ISSUES DETECTED ⚠"}</strong>
            <div className="muted small">{health.root_path}</div>
          </div>
          {canRepair && (
            <Button kind="primary" disabled={busy} onClick={() => void handleRepair()}>
              {busy ? "Repairing…" : "Run Safe Repair"}
            </Button>
          )}
        </div>

        {repairResult && <div className="info-note">{repairResult}</div>}

        <div className="audit-sections" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
          <div
            style={{
              background: "var(--surface-secondary)",
              border: "1px solid var(--line)",
              borderRadius: "8px",
              padding: "12px",
            }}
          >
            <h4 style={{ margin: "0 0 8px 0" }}>SQLite Database</h4>
            <div className="small muted">Integrity: <strong>{health.database?.integrity ?? "unknown"}</strong></div>
            <div className="small muted">People Count: <strong>{health.database?.people_count ?? 0}</strong></div>
            <div className="small muted">Parent-Child Facts: <strong>{health.database?.parent_child_count ?? 0}</strong></div>
            <div className="small muted">Marriages Count: <strong>{health.database?.marriages_count ?? 0}</strong></div>
          </div>

          <div
            style={{
              background: "var(--surface-secondary)",
              border: "1px solid var(--line)",
              borderRadius: "8px",
              padding: "12px",
            }}
          >
            <h4 style={{ margin: "0 0 8px 0" }}>Filesystem Synchronization</h4>
            <div className="small muted">Missing Person Folders: {health.filesystem?.missing_person_folders.length ?? 0}</div>
            <div className="small muted">Missing Journals: {health.filesystem?.missing_journals.length ?? 0}</div>
            <div className="small muted">Orphan Person Folders: {health.filesystem?.orphan_person_folders.length ?? 0}</div>
            <div className="small muted">Archived-Active Mismatches: {health.filesystem?.archived_active_mismatches.length ?? 0}</div>
          </div>
        </div>

        <div>
          <h4 style={{ margin: "0 0 8px 0" }}>Issues Log ({health.issues.length})</h4>
          {health.issues.length === 0 ? (
            <div className="muted small">No issues detected. Database and filesystem are 100% synchronized.</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "6px", maxHeight: "200px", overflowY: "auto" }}>
              {health.issues.map((issue, idx) => (
                <div
                  key={idx}
                  style={{
                    padding: "8px 10px",
                    borderRadius: "6px",
                    background: issue.severity === "error" ? "var(--danger-soft)" : "var(--warn-soft)",
                    border: `1px solid ${issue.severity === "error" ? "var(--danger)" : "var(--warn)"}`,
                    fontSize: "12.5px",
                  }}
                >
                  <strong>[{issue.code}]</strong> {issue.message}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}
