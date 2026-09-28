import { useState } from "react";
import { api } from "../../../api";
import { Button, ErrorNote, Modal } from "../../../components/ui";
import type { BackupInfo } from "../../../types";
import { RestoreProgress, type RestoreStage } from "./RestoreProgress";

export function RestoreBackupDialog({
  backup,
  onClose,
  onSuccess,
}: {
  backup: BackupInfo;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [tokenInput, setTokenInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState<RestoreStage | null>(null);
  const [error, setError] = useState<unknown>(null);

  async function handleRestore() {
    if (tokenInput !== "RESTORE" || !backup.verified || !backup.compatibility.ok) return;
    setBusy(true);
    setError(null);
    setStage("verifying");
    try {
      const verification = await api.backups.verify(backup.id);
      if (!verification.ok) throw new Error("Backup verification failed. Restore was not started.");
      setStage("restoring");
      await api.backups.restore(backup.id, "RESTORE");
      setStage("complete");
    } catch (err) {
      setError(err);
      setStage(null);
    } finally {
      setBusy(false);
    }
  }

  if (stage === "complete") {
    return (
      <section
        className="card"
        aria-label={`Restore Backup: ${backup.label || backup.name}`}
        style={{ marginTop: 16 }}
      >
        <RestoreProgress currentStage="complete" />
        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 12 }}>
          <Button kind="primary" onClick={onSuccess}>Reload Restored Data</Button>
        </div>
      </section>
    );
  }

  return (
    <Modal title={`Restore Backup: ${backup.label || backup.name}`} onClose={() => !busy && onClose()}>
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ background: "var(--warn-soft)", border: "1px solid var(--warn)", borderRadius: 8, padding: 12, fontSize: 13, color: "var(--warn)" }}>
          <strong>Current data will be replaced</strong>
          <p style={{ margin: "4px 0 0" }}>The current database, People folders, Journals, and portable Config will be replaced with this verified backup state.</p>
          <p style={{ margin: "4px 0 0" }}>A verified Safety / Pre-Restore snapshot of the current state must complete before any active data changes.</p>
        </div>

        <div style={{ background: "var(--surface-secondary)", padding: "10px 12px", borderRadius: 8, border: "1px solid var(--line)", fontSize: 12.5 }}>
          <div>Label: <strong>{backup.label || "Snapshot"}</strong></div>
          <div>Created: <strong>{backup.created || "Unknown"}</strong></div>
          <div>Category: <strong>{backup.category}{backup.safety_reason ? ` / ${backup.safety_reason.replace(/_/g, " ")}` : ""}</strong></div>
          <div>People / Journals: <strong>{backup.person_count ?? 0} / {backup.journal_count ?? 0}</strong></div>
          <div>Size / Schema: <strong>{backup.total_size_bytes ?? 0} bytes / {backup.schema_version ?? "unknown"}</strong></div>
          <div>Verification / Compatibility: <strong>{backup.integrity_status} / {backup.compatibility.status}</strong></div>
        </div>

        {stage ? <RestoreProgress currentStage={stage} /> : (
          <div>
            <label className="small muted" htmlFor="restore-confirmation" style={{ display: "block", marginBottom: 6 }}>
              Type <strong>RESTORE</strong> exactly to continue:
            </label>
            <input id="restore-confirmation" value={tokenInput} onChange={(event) => setTokenInput(event.target.value)} disabled={busy} autoComplete="off" placeholder="RESTORE" />
          </div>
        )}

        <ErrorNote error={error} />
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <Button kind="ghost" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button kind="danger" disabled={busy || tokenInput !== "RESTORE" || !backup.verified || !backup.compatibility.ok} onClick={() => void handleRestore()}>
            {busy ? "Restoring…" : "Confirm Restore"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
