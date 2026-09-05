import { useState } from "react";
import { Button } from "../../components/ui";

export interface StartupFailureViewProps {
  port?: number;
  errorMessage?: string;
  onRetry: () => void;
}

export function StartupFailureView({
  port,
  errorMessage,
  onRetry,
}: StartupFailureViewProps) {
  const [showDetails, setShowDetails] = useState(false);
  const [retrying, setRetrying] = useState(false);

  async function handleRetry() {
    setRetrying(true);
    try {
      await onRetry();
    } finally {
      setRetrying(false);
    }
  }

  async function handleOpenFolder() {
    if (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window) {
      try {
        const { invoke } = await import("@tauri-apps/api/core");
        await invoke("open_path", { path: "." });
      } catch (err) {
        console.error("Could not open path via Tauri:", err);
      }
    }
  }

  async function handleExit() {
    if (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window) {
      try {
        const { invoke } = await import("@tauri-apps/api/core");
        await invoke("exit_app");
      } catch {
        window.close();
      }
    } else {
      window.close();
    }
  }

  return (
    <div className="root-unavailable-overlay">
      <div className="root-unavailable-modal" style={{ maxWidth: 540 }}>
        <div className="modal-header">
          <div className="warning-icon" style={{ background: "#fee2e2", color: "#dc2626" }}>
            ⚠
          </div>
          <div>
            <h2>Data Service Unavailable</h2>
            <p className="subtitle">
              People Relationships could not start its local data service.
            </p>
          </div>
        </div>

        <div className="modal-body" style={{ marginTop: 16 }}>
          <p style={{ color: "var(--color-muted, #64748b)", lineHeight: 1.6, fontSize: 14 }}>
            The background application service on loopback address <code>127.0.0.1</code> did not
            respond to health checks within the startup window. Your relationship data and journals
            are safe on disk.
          </p>

          <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginTop: 20 }}>
            <Button
              kind="primary"
              disabled={retrying}
              onClick={() => void handleRetry()}
            >
              {retrying ? "Retrying…" : "Retry Connection"}
            </Button>
            <Button
              kind="default"
              onClick={() => void handleOpenFolder()}
            >
              Open Application Folder
            </Button>
            <Button
              kind="ghost"
              onClick={() => setShowDetails((v) => !v)}
            >
              {showDetails ? "Hide Details" : "Show Technical Details"}
            </Button>
            <Button
              kind="danger"
              onClick={() => void handleExit()}
            >
              Exit
            </Button>
          </div>

          {showDetails && (
            <div
              style={{
                marginTop: 16,
                padding: 12,
                borderRadius: 6,
                background: "var(--color-bg-subtle, #f1f5f9)",
                border: "1px solid var(--color-border, #cbd5e1)",
                fontSize: 12,
                fontFamily: "monospace",
                color: "#334155",
                whiteSpace: "pre-wrap",
                wordBreak: "break-all",
              }}
            >
              <div><strong>Port:</strong> {port ?? "default (8765)"}</div>
              <div><strong>Endpoint:</strong> http://127.0.0.1:{port ?? 8765}/api/health</div>
              <div><strong>Diagnostics:</strong> {errorMessage || "Connection timed out during startup readiness check."}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
