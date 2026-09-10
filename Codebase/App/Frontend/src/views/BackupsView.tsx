import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { Button, ErrorNote, Modal } from "../components/ui";
import { BackupDetailsDialog } from "../features/backups/components/BackupDetailsDialog";
import { RestoreBackupDialog } from "../features/backups/components/RestoreBackupDialog";
import { DataRootPanel } from "../features/dataRoot/components/DataRootPanel";
import { openFolder } from "../openPath";
import type { BackupInfo, BackupVerification } from "../types";

const SECTIONS: Array<{ id: BackupInfo["category"]; title: string; note: string }> = [
  { id: "manual", title: "Manual", note: "Snapshots you create before important changes." },
  { id: "automatic", title: "Automatic", note: "Supported category; scheduling is not configured in V1." },
  { id: "safety", title: "Safety", note: "Verified snapshots created before restore and maintenance operations." },
  { id: "legacy", title: "Legacy", note: "Older top-level snapshots remain in place and usable when valid." },
];

function formatSize(bytes?: number) {
  if (bytes == null) return "Unknown size";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function BackupsView() {
  const [backups, setBackups] = useState<BackupInfo[]>([]);
  const [readOnly, setReadOnly] = useState(false);
  const [maintenance, setMaintenance] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [createLabel, setCreateLabel] = useState("");
  const [creating, setCreating] = useState(false);
  const [verifying, setVerifying] = useState<string | null>(null);
  const [verification, setVerification] = useState<{ backup: BackupInfo; result: BackupVerification } | null>(null);
  const [details, setDetails] = useState<BackupInfo | null>(null);
  const [restore, setRestore] = useState<BackupInfo | null>(null);

  const load = useCallback(async () => {
    try {
      const [backupResult, rootStatus] = await Promise.all([api.backups.list(), api.dataRoot.status()]);
      setBackups(backupResult.backups);
      setReadOnly(rootStatus.read_only);
      setMaintenance(rootStatus.maintenance_locked ? rootStatus.maintenance_operation || "Maintenance" : null);
      setError(null);
    } catch (err) {
      setError(err);
    }
  }, []);

  useEffect(() => void load(), [load]);

  async function create() {
    setCreating(true);
    setInfo(null);
    setError(null);
    try {
      const result = await api.backups.create(createLabel.trim() || undefined);
      setCreateOpen(false);
      setCreateLabel("");
      setInfo(`Verified backup created: ${result.backup.name}`);
      await load();
    } catch (err) {
      setError(err);
    } finally {
      setCreating(false);
    }
  }

  async function verify(backup: BackupInfo) {
    setVerifying(backup.id);
    setError(null);
    try {
      const result = await api.backups.verify(backup.id);
      setVerification({ backup, result });
      await load();
    } catch (err) {
      setError(err);
    } finally {
      setVerifying(null);
    }
  }

  async function openBackup(backup: BackupInfo) {
    const message = await openFolder(backup.path);
    if (!message.startsWith("Opened")) setError(new Error(message));
    else setInfo(message);
  }

  const writesBlocked = readOnly || Boolean(maintenance);

  return (
    <div className="view">
      <div className="view-head">
        <div>
          <h1>Backups & Recovery</h1>
          <p className="muted">Verified local snapshots of the database, People, Journals, and portable Config.</p>
        </div>
        <Button kind="primary" disabled={writesBlocked || creating} onClick={() => setCreateOpen(true)}>
          Create Backup
        </Button>
      </div>

      <DataRootPanel onDataChanged={load} />
      {readOnly && <div className="info-note">Data root is read-only. Listing, details, verification, and Open Folder remain available; create and restore are blocked.</div>}
      {maintenance && <div className="info-note">{maintenance} is in progress. Create and restore are temporarily blocked.</div>}
      <ErrorNote error={error} />
      {info && <div className="info-note">{info}</div>}

      {SECTIONS.map((section) => {
        const items = backups.filter((backup) => backup.category === section.id);
        return (
          <section className="backup-section" key={section.id} aria-label={`${section.title} backups`}>
            <div className="backups-header">
              <div>
                <h3>{section.title}</h3>
                <div className="muted tiny">{section.note}</div>
              </div>
              <span className="chip">{items.length}</span>
            </div>
            <div className="backup-list">
              {items.length === 0 && <div className="empty-state">No {section.title.toLowerCase()} backups.</div>}
              {items.map((backup) => {
                const canRestore = backup.verified && backup.compatibility.ok && !writesBlocked;
                return (
                  <div className="backup-row" key={`${backup.category}-${backup.id}`} data-backup-id={backup.id}>
                    <div>
                      <strong>{backup.label || backup.name}</strong>
                      <div className="muted small">{backup.created || "Unknown date"} · {backup.category}{backup.safety_reason ? ` / ${backup.safety_reason.replace(/_/g, " ")}` : ""}</div>
                      <div className="muted tiny">{backup.name}</div>
                    </div>
                    <div className="backup-meta">
                      <span className="chip">{formatSize(backup.total_size_bytes)}</span>
                      <span className="chip">{backup.person_count ?? 0} people</span>
                      <span className="chip">{backup.journal_count ?? 0} Journals</span>
                      <span className={`chip ${backup.verified ? "chip-group" : ""}`}>
                        {backup.verified ? "Verified ✓" : backup.integrity_status}
                      </span>
                    </div>
                    <div className="row-actions">
                      <Button kind="ghost" onClick={() => setDetails(backup)}>View Details</Button>
                      <Button kind="ghost" disabled={verifying === backup.id} onClick={() => void verify(backup)}>
                        {verifying === backup.id ? "Verifying…" : "Verify"}
                      </Button>
                      <Button kind="ghost" onClick={() => void openBackup(backup)}>Open Folder</Button>
                      <Button kind="primary" disabled={!canRestore} title={!canRestore ? "Verify a compatible backup and ensure the Data Root is writable." : undefined} onClick={() => setRestore(backup)}>
                        Restore
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        );
      })}

      {createOpen && (
        <Modal title="Create Manual Backup" onClose={() => !creating && setCreateOpen(false)}>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <p className="muted small">This verified snapshot includes the SQLite database, all People folders and Journals, and portable Config. Backups are never copied into themselves.</p>
            <label className="small" htmlFor="backup-label"><strong>Label</strong> (optional)</label>
            <input id="backup-label" value={createLabel} disabled={creating} onChange={(event) => setCreateLabel(event.target.value)} placeholder="Before an important change" autoFocus />
            <div className="muted tiny">Category: Manual</div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
              <Button kind="ghost" disabled={creating} onClick={() => setCreateOpen(false)}>Cancel</Button>
              <Button kind="primary" disabled={creating} onClick={() => void create()}>{creating ? "Creating and verifying…" : "Create Backup"}</Button>
            </div>
          </div>
        </Modal>
      )}

      {verification && (
        <Modal title={verification.result.ok ? "Backup Verified ✓" : "Verification Failed"} onClose={() => setVerification(null)}>
          <p>{verification.result.ok ? "Every manifested file, byte size, SHA-256 hash, count, schema, and SQLite integrity check passed." : "This backup cannot be restored until these problems are resolved:"}</p>
          {!verification.result.ok && (
            <ul>{verification.result.issues.map((issue, index) => <li key={`${issue.code}-${index}`}><strong>{issue.code}</strong>: {issue.message}{issue.path ? ` (${issue.path})` : ""}</li>)}</ul>
          )}
          <div className="muted small">Database: {verification.result.db_integrity} · Schema: {verification.result.compatibility.status}</div>
        </Modal>
      )}

      {details && <BackupDetailsDialog backup={details} onClose={() => setDetails(null)} />}
      {restore && (
        <RestoreBackupDialog
          backup={restore}
          onClose={() => setRestore(null)}
          onSuccess={() => {
            setRestore(null);
            window.location.reload();
          }}
        />
      )}
    </div>
  );
}
