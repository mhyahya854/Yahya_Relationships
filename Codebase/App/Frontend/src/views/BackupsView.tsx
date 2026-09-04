import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { Button, ErrorNote } from "../components/ui";
import { BackupDetailsDialog } from "../features/backups/components/BackupDetailsDialog";
import { RestoreBackupDialog } from "../features/backups/components/RestoreBackupDialog";
import { DataRootPanel } from "../features/dataRoot/components/DataRootPanel";
import { openFolder } from "../openPath";
import type { BackupInfo } from "../types";

export function BackupsView() {
  const [backups, setBackups] = useState<BackupInfo[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [info, setInfo] = useState<string | null>(null);
  const [selectedBackupForDetails, setSelectedBackupForDetails] = useState<BackupInfo | null>(null);
  const [selectedBackupForRestore, setSelectedBackupForRestore] = useState<BackupInfo | null>(null);

  const load = useCallback(async () => {
    try {
      const result = await api.backups.list();
      setBackups(result.backups);
      setError(null);
    } catch (err) {
      setError(err);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function create(label?: string) {
    setBusy(true);
    setInfo(null);
    try {
      const result = await api.backups.create(label);
      setInfo(`Backup created: ${result.backup.name} (${result.backup.files} files)`);
      await load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function verify(name: string) {
    try {
      const result = await api.backups.verify(name);
      const isOk = result.ok || result.ok_backup;
      window.alert(
        isOk
          ? `Backup Verified ✓ — All files verified against manifest.`
          : `Problems found:\n${(result.problems || result.issues || []).join("\n")}`,
      );
    } catch (err) {
      setError(err);
    }
  }

  async function openBackup(backup: BackupInfo) {
    const message = await openFolder(backup.path);
    if (message && !message.startsWith("Opened")) {
      window.alert(message);
    }
  }

  return (
    <div className="view">
      <div className="view-head">
        <div>
          <h1>Backups & Data Safety</h1>
          <p className="muted">
            authoritative Data Root, timestamped local snapshots, guided restore with safety backups, and filesystem synchronization.
          </p>
        </div>
        <Button
          kind="primary"
          disabled={busy}
          onClick={() => {
            const label = window.prompt("Backup label (optional)");
            void create(label?.trim() || undefined);
          }}
        >
          Create Backup
        </Button>
      </div>

      <DataRootPanel onDataChanged={load} />

      <ErrorNote error={error} />
      {info && <div className="info-note">{info}</div>}

      <div className="backups-header" style={{ margin: "16px 0 8px 0" }}>
        <h3 style={{ margin: 0, fontSize: "16px" }}>Local Snapshot Backups</h3>
      </div>

      <div className="backup-list">
        {backups.length === 0 && (
          <div className="empty-state">
            No backups yet. Create one to snapshot the whole personal data state.
          </div>
        )}
        {backups.map((backup) => (
          <div className="backup-row" key={backup.name}>
            <div>
              <strong>{backup.label || backup.name}</strong>
              <div className="muted small">
                {backup.name}
                {backup.created ? ` · ${backup.created}` : ""}
              </div>
              <div className="muted tiny">{backup.path}</div>
            </div>
            <div className="backup-meta">
              {backup.files != null && (
                <span className="chip">{backup.files} files</span>
              )}
              {backup.has_manifest && (
                <span className="chip chip-group">manifest</span>
              )}
            </div>
            <div className="row-actions">
              <Button
                kind="ghost"
                onClick={() => setSelectedBackupForDetails(backup)}
              >
                View Details
              </Button>
              <Button kind="ghost" onClick={() => void verify(backup.name)}>
                Verify
              </Button>
              <Button
                kind="ghost"
                onClick={() => void openBackup(backup)}
              >
                Open Folder
              </Button>
              <Button
                kind="primary"
                onClick={() => setSelectedBackupForRestore(backup)}
              >
                Restore
              </Button>
            </div>
          </div>
        ))}
      </div>

      {selectedBackupForDetails && (
        <BackupDetailsDialog
          backup={selectedBackupForDetails}
          onClose={() => setSelectedBackupForDetails(null)}
        />
      )}

      {selectedBackupForRestore && (
        <RestoreBackupDialog
          backup={selectedBackupForRestore}
          onClose={() => setSelectedBackupForRestore(null)}
          onSuccess={() => {
            setSelectedBackupForRestore(null);
            void load();
            window.location.reload();
          }}
        />
      )}
    </div>
  );
}
