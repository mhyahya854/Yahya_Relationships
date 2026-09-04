import { useState } from "react";
import { Button, ErrorNote } from "../../../components/ui";
import { dataRootApi } from "../api";

export function RootUnavailableView({
  lastLocation,
  onRecovered,
}: {
  lastLocation?: string;
  onRecovered: () => void;
}) {
  const [targetPath, setTargetPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [showSwitchInput, setShowSwitchInput] = useState(false);

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

  async function handleSwitch() {
    if (!targetPath.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await dataRootApi.switch(targetPath.trim());
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
          maxWidth: "520px",
          background: "#ffffff",
          border: "1px solid var(--line, #e2e8f0)",
          borderRadius: "12px",
          padding: "32px",
          boxShadow: "0 10px 25px rgba(0,0,0,0.08)",
        }}
      >
        <div style={{ fontSize: "42px", marginBottom: "12px" }}>⚠</div>
        <h2 style={{ margin: "0 0 8px 0" }}>People Relationships Data Unavailable</h2>
        <p className="muted" style={{ fontSize: "14px", marginBottom: "20px" }}>
          The active relationship data folder could not be found or opened. This usually happens if an external drive was disconnected.
        </p>

        {lastLocation && (
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

        {!showSwitchInput ? (
          <div style={{ display: "flex", gap: "10px", justifyContent: "center", marginTop: "16px" }}>
            <Button kind="primary" disabled={busy} onClick={() => void handleRetry()}>
              {busy ? "Retrying…" : "Retry"}
            </Button>
            <Button kind="default" onClick={() => setShowSwitchInput(true)}>
              Choose Existing Data Root
            </Button>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "10px", marginTop: "16px" }}>
            <input
              type="text"
              placeholder="Enter valid Data Root directory path…"
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
              <Button kind="ghost" onClick={() => setShowSwitchInput(false)}>
                Cancel
              </Button>
              <Button kind="primary" disabled={busy || !targetPath.trim()} onClick={() => void handleSwitch()}>
                Switch Data Root
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
