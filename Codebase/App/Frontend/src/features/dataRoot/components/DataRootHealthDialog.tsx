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

  async function handleRepair() {
    setBusy(true);
    setRepairResult(null);
    try {
      const res = await dataRootApi.repair();
      if (res.ok) {
        setRepairResult(`Repaired ${res.repaired} non-destructive item(s).`);
        onRefresh();
      } else {
        setRepairResult(`Repair attempted: ${res.errors.join(", ")}`);
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
            background: health.ok ? "var(--ok-soft, #eef9f5)" : "var(--warn-soft, #fff8ec)",
            border: `1px solid ${health.ok ? "var(--ok, #2e7d32)" : "var(--warn, #d97706)"}`,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div>
            <strong>Status: {health.ok ? "HEALTHY ✓" : "ISSUES DETECTED ⚠"}</strong>
            <div className="muted small">{health.active_root}</div>
          </div>
          {!health.ok && (
            <Button kind="primary" disabled={busy} onClick={() => void handleRepair()}>
              {busy ? "Repairing…" : "Run Safe Repair"}
            </Button>
          )}
        </div>

        {repairResult && <div className="info-note">{repairResult}</div>}

        <div className="audit-sections" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
          <div
            style={{
              background: "#f8fafc",
              border: "1px solid #e2e8f0",
              borderRadius: "8px",
              padding: "12px",
            }}
          >
            <h4 style={{ margin: "0 0 8px 0" }}>SQLite Database</h4>
            <div className="small muted">Integrity: <strong>{health.database?.integrity ?? "unknown"}</strong></div>
            <div className="small muted">People Count: <strong>{health.database?.people_count ?? 0}</strong></div>
            <div className="small muted">Parent-Child Facts: <strong>{health.database?.parent_child_facts_count ?? 0}</strong></div>
            <div className="small muted">Marriages Count: <strong>{health.database?.marriages_count ?? 0}</strong></div>
          </div>

          <div
            style={{
              background: "#f8fafc",
              border: "1px solid #e2e8f0",
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
                    background: issue.severity === "error" ? "#fef2f2" : "#fffbe6",
                    border: `1px solid ${issue.severity === "error" ? "#fecaca" : "#ffe58f"}`,
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
