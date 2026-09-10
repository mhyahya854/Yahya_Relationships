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
    if (!status?.active_root) return;
    const msg = await openFolder(status.active_root);
    if (msg && !msg.startsWith("Opened")) {
      setError(new Error(msg));
    }
  }

  if (!status) {
    return <div className="panel muted">Loading Data Safety Status…</div>;
  }

  const isHealthy = status.state === "HEALTHY";

  return (
    <div className="data-root-panel">
      <div className="data-root-panel-row">
        <div>
          <div className="data-root-heading">
            <h3>Active Data Root Location</h3>
            <span className={`status-pill ${isHealthy ? "status-success" : "status-warning"}`}>
              {status.state.replace(/_/g, " ")}{isHealthy ? " ✓" : ""}
            </span>
          </div>
          <code className="path-value" title={status.active_root ?? undefined}>
            {status.active_root ?? "No active location"}
          </code>
        </div>

        <div className="data-root-actions">
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
          activeRoot={status.active_root ?? ""}
          onClose={() => setShowChangeLocation(false)}
        />
      )}
    </div>
  );
}
