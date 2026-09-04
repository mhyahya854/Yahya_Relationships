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
  backup: BackupInfo & {
    timestamp?: string;
    person_count?: number;
    journal_count?: number;
  };
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [tokenInput, setTokenInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState<RestoreStage | null>(null);
  const [error, setError] = useState<unknown>(null);

  async function handleRestore() {
    if (tokenInput.trim() !== "RESTORE") return;
    setBusy(true);
    setError(null);
    setStage("verifying");

    try {
      // Step 1: Precheck / verify
      await api.backups.verify(backup.name);

      // Step 2: Progress through restore stages
      setStage("safety_backup");
      await new Promise((r) => setTimeout(r, 400));
      setStage("staging");
      await new Promise((r) => setTimeout(r, 400));
      setStage("validating");

      // Execute atomic restore
      const res = await api.backups.restore(backup.name, "RESTORE");

      setStage("switching");
      await new Promise((r) => setTimeout(r, 400));
      setStage("complete");

      setTimeout(() => {
        onSuccess();
      }, 1000);
    } catch (err) {
      setError(err);
      setStage(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={`Restore Backup: ${backup.label || backup.name}`} onClose={onClose}>
      <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
        <div
          style={{
            background: "#fffbe6",
            border: "1px solid #ffe58f",
            borderRadius: "8px",
            padding: "12px",
            fontSize: "13px",
            color: "#8c6b00",
          }}
        >
          <strong>⚠ Important Data Safety Guarantee</strong>
          <p style={{ margin: "4px 0 0 0" }}>
            Restoring this backup will replace your current SQLite database and journals with the state from{" "}
            <strong>{backup.created || backup.timestamp || backup.name}</strong>.
          </p>
          <p style={{ margin: "4px 0 0 0" }}>
            A safety snapshot of your current state will automatically be created first (e.g. <code>pre-restore-...</code>).
          </p>
        </div>

        <div style={{ background: "#f8fafc", padding: "10px 12px", borderRadius: "8px", border: "1px solid #e2e8f0", fontSize: "12.5px" }}>
          <div>Backup Label: <strong>{backup.label || "Snapshot"}</strong></div>
          <div>Backup Timestamp: <strong>{backup.created || backup.timestamp || "N/A"}</strong></div>
          {backup.person_count != null && <div>People Included: <strong>{backup.person_count}</strong></div>}
          {backup.journal_count != null && <div>Journals Included: <strong>{backup.journal_count}</strong></div>}
        </div>

        {stage ? (
          <RestoreProgress currentStage={stage} />
        ) : (
          <div>
            <label className="small muted" style={{ display: "block", marginBottom: "6px" }}>
              To confirm restore, type <strong>RESTORE</strong> below:
            </label>
            <input
              type="text"
              placeholder="Type RESTORE to confirm"
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
              disabled={busy}
              style={{
                width: "100%",
                padding: "8px 10px",
                borderRadius: "6px",
                border: "1px solid #ccc",
                fontSize: "13px",
              }}
            />
          </div>
        )}

        <ErrorNote error={error} />

        {!stage && (
          <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "8px" }}>
            <Button kind="ghost" onClick={onClose} disabled={busy}>
              Cancel
            </Button>
            <Button
              kind="danger"
              disabled={busy || tokenInput.trim() !== "RESTORE"}
              onClick={() => void handleRestore()}
            >
              Confirm Restore
            </Button>
          </div>
        )}
      </div>
    </Modal>
  );
}
