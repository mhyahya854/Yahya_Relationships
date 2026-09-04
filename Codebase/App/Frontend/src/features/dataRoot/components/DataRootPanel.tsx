import { useCallback, useEffect, useState } from "react";
import { Button, ErrorNote } from "../../../components/ui";
import { openFolder } from "../../../openPath";
import { dataRootApi } from "../api";
import type { DataRootStatus } from "../types";
import { ChangeDataRootDialog } from "./ChangeDataRootDialog";
import { DataRootHealthDialog } from "./DataRootHealthDialog";

export function DataRootPanel({ onDataChanged }: { onDataChanged?: () => void }) {
  const [status, setStatus] = useState<DataRootStatus | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [showHealth, setShowHealth] = useState(false);
  const [showChangeLocation, setShowChangeLocation] = useState(false);

  const loadStatus = useCallback(async () => {
    try {
      const data = await dataRootApi.getStatus();
      setStatus(data);
      setError(null);
    } catch (err) {
      setError(err);
    }
  }, []);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  async function handleOpenFolder() {
    if (!status) return;
    const msg = await openFolder(status.active_root);
    if (msg && !msg.startsWith("Opened")) {
      window.alert(msg);
    }
  }

  if (!status) {
    return <div className="panel muted">Loading Data Safety Status…</div>;
  }

  const isHealthy = status.health.ok;

  return (
    <div
      className="data-root-panel"
      style={{
        background: "#ffffff",
        border: "1px solid var(--line, #e2e8f0)",
        borderRadius: "10px",
        padding: "16px",
        marginBottom: "20px",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "12px" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
            <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 600 }}>Active Data Root Location</h3>
            <span
              style={{
                fontSize: "11px",
                padding: "2px 8px",
                borderRadius: "999px",
                fontWeight: 600,
                background: isHealthy ? "var(--ok-soft, #eef9f5)" : "var(--warn-soft, #fff8ec)",
                color: isHealthy ? "var(--ok, #2e7d32)" : "var(--warn, #d97706)",
                border: `1px solid ${isHealthy ? "#b7eb8f" : "#ffe58f"}`,
              }}
            >
              {isHealthy ? "Verified Healthy ✓" : "Audit Issues Found ⚠"}
            </span>
          </div>
          <code style={{ fontSize: "12.5px", background: "#f1f5f9", padding: "2px 6px", borderRadius: "4px" }}>
            {status.active_root}
          </code>
        </div>

        <div style={{ display: "flex", gap: "8px" }}>
          <Button kind="default" onClick={() => void handleOpenFolder()}>
            Open Folder
          </Button>
          <Button kind="default" onClick={() => setShowHealth(true)}>
            Validate
          </Button>
          <Button kind="default" onClick={() => setShowChangeLocation(true)}>
            Change Location
          </Button>
        </div>
      </div>

      <ErrorNote error={error} />

      {showHealth && status && (
        <DataRootHealthDialog
          health={status.health}
          onClose={() => setShowHealth(false)}
          onRefresh={() => {
            void loadStatus();
            onDataChanged?.();
          }}
        />
      )}

      {showChangeLocation && status && (
        <ChangeDataRootDialog
          activeRoot={status.active_root}
          onClose={() => setShowChangeLocation(false)}
          onSuccess={() => {
            setShowChangeLocation(false);
            void loadStatus();
            onDataChanged?.();
          }}
        />
      )}
    </div>
  );
}
