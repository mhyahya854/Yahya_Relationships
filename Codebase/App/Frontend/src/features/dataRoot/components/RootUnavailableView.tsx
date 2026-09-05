import { useState } from "react";
import { Button, ErrorNote } from "../../../components/ui";
import { dataRootApi } from "../api";

export function RootUnavailableView({
  firstRun = false,
  lastLocation,
  onRecovered,
}: {
  firstRun?: boolean;
  lastLocation?: string;
  onRecovered: () => void;
}) {
  const [targetPath, setTargetPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [manualAction, setManualAction] = useState<"switch" | "restore" | "init" | null>(null);

  async function pickFolderNative(): Promise<string | null> {
    if (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window) {
      try {
        const { invoke } = await import("@tauri-apps/api/core");
        const chosen = await invoke<string | null>("pick_folder");
        if (chosen) return chosen;
      } catch (err) {
        console.warn("Native folder picker unavailable, falling back to input:", err);
      }
    }
    return null;
  }

  async function handleRetry() {
    setBusy(true);
    setError(null);
    try {
      const status = await dataRootApi.getStatus();
      if (status.health.ok) {
        onRecovered();
      } else {
        setError(new Error("Data root is still unavailable or corrupted."));
      }
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function handleUseExisting() {
    setError(null);
    const chosen = await pickFolderNative();
    if (chosen) {
      setBusy(true);
      try {
        await dataRootApi.switch(chosen);
        onRecovered();
      } catch (err) {
        setError(err);
      } finally {
        setBusy(false);
      }
    } else {
      setManualAction("switch");
    }
  }

  async function handleRestoreBackup() {
    setError(null);
    const chosen = await pickFolderNative();
    if (chosen) {
      setBusy(true);
      try {
        await dataRootApi.restoreTo(chosen);
        onRecovered();
      } catch (err) {
        setError(err);
      } finally {
        setBusy(false);
      }
    } else {
      setManualAction("restore");
    }
  }

  async function handleCreateNew() {
    setError(null);
    const chosen = await pickFolderNative();
    if (chosen) {
      setBusy(true);
      try {
        await dataRootApi.initialize(chosen);
        onRecovered();
      } catch (err) {
        setError(err);
      } finally {
        setBusy(false);
      }
    } else {
      setManualAction("init");
    }
  }

  async function handleManualSubmit() {
    if (!targetPath.trim()) return;
    setBusy(true);
    setError(null);
    try {
      if (manualAction === "switch") {
        await dataRootApi.switch(targetPath.trim());
      } else if (manualAction === "restore") {
        await dataRootApi.restoreTo(targetPath.trim());
      } else if (manualAction === "init") {
        await dataRootApi.initialize(targetPath.trim());
      }
      onRecovered();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="root-unavailable-view"
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "80vh",
        padding: "24px",
        textAlign: "center",
      }}
    >
      <div
        style={{
          maxWidth: "560px",
          width: "100%",
          background: "#ffffff",
          border: "1px solid var(--line, #e2e8f0)",
          borderRadius: "12px",
          padding: "36px",
          boxShadow: "0 10px 25px rgba(0,0,0,0.08)",
        }}
      >
        <div style={{ fontSize: "42px", marginBottom: "12px" }}>
          {firstRun ? "❖" : "⚠"}
        </div>
        <h2 style={{ margin: "0 0 8px 0" }}>
          {firstRun ? "Welcome to People Relationships" : "Data could not be found"}
        </h2>
        <p className="muted" style={{ fontSize: "14px", marginBottom: "20px" }}>
          {firstRun
            ? "Get started by selecting an existing relationship data directory, restoring from a backup archive, or creating a brand-new database."
            : "The active relationship data folder could not be found or opened. This usually happens if an external drive was disconnected."}
        </p>

        {!firstRun && lastLocation && (
          <div
            style={{
              background: "#f8fafc",
              border: "1px solid #e2e8f0",
              borderRadius: "8px",
              padding: "10px",
              fontSize: "12px",
              marginBottom: "20px",
            }}
          >
            <div className="muted small">Last known location:</div>
            <code>{lastLocation}</code>
          </div>
        )}

        <ErrorNote error={error} />

        {manualAction === null ? (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "10px",
              marginTop: "20px",
            }}
          >
            {firstRun ? (
              <>
                <Button kind="primary" disabled={busy} onClick={() => void handleUseExisting()}>
                  Use Existing Data Folder
                </Button>
                <Button kind="default" disabled={busy} onClick={() => void handleRestoreBackup()}>
                  Restore From Backup
                </Button>
                <Button kind="default" disabled={busy} onClick={() => void handleCreateNew()}>
                  Create New Relationship Database
                </Button>
              </>
            ) : (
              <div style={{ display: "flex", gap: "10px", justifyContent: "center" }}>
                <Button kind="primary" disabled={busy} onClick={() => void handleRetry()}>
                  {busy ? "Retrying…" : "Retry"}
                </Button>
                <Button kind="default" disabled={busy} onClick={() => void handleUseExisting()}>
                  Choose Existing Data Root
                </Button>
                <Button kind="default" disabled={busy} onClick={() => void handleRestoreBackup()}>
                  Restore Backup
                </Button>
              </div>
            )}
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginTop: "16px" }}>
            <input
              type="text"
              placeholder={
                manualAction === "switch"
                  ? "Enter valid Data Root directory path…"
                  : manualAction === "restore"
                  ? "Enter backup directory path to restore…"
                  : "Enter destination path for new database…"
              }
              value={targetPath}
              onChange={(e) => setTargetPath(e.target.value)}
              style={{
                padding: "8px 10px",
                borderRadius: "6px",
                border: "1px solid #ccc",
                fontSize: "13px",
              }}
            />
            <div style={{ display: "flex", gap: "8px", justifyContent: "flex-end" }}>
              <Button kind="ghost" onClick={() => setManualAction(null)}>
                Cancel
              </Button>
              <Button
                kind="primary"
                disabled={busy || !targetPath.trim()}
                onClick={() => void handleManualSubmit()}
              >
                {busy ? "Processing…" : "Submit"}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
