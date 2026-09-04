import { useState } from "react";
import { Button, ErrorNote, Modal } from "../../../components/ui";
import { dataRootApi } from "../api";

export function ChangeDataRootDialog({
  activeRoot,
  onClose,
  onSuccess,
}: {
  activeRoot: string;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [mode, setMode] = useState<"move" | "switch">("move");
  const [targetPath, setTargetPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [info, setInfo] = useState<string | null>(null);

  async function handleSubmit() {
    if (!targetPath.trim()) return;
    setBusy(true);
    setError(null);
    setInfo(null);

    try {
      if (mode === "move") {
        const res = await dataRootApi.move(targetPath.trim());
        setInfo(`Successfully moved active Data Root to ${res.new_root}`);
      } else {
        const res = await dataRootApi.switch(targetPath.trim());
        setInfo(`Switched active Data Root to ${res.active_root}`);
      }
      setTimeout(() => {
        onSuccess();
      }, 1200);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Change Data Location" onClose={onClose}>
      <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
        <div style={{ display: "flex", gap: "8px" }}>
          <Button
            kind={mode === "move" ? "primary" : "default"}
            onClick={() => setMode("move")}
          >
            Move Current Data
          </Button>
          <Button
            kind={mode === "switch" ? "primary" : "default"}
            onClick={() => setMode("switch")}
          >
            Use Existing Data Root
          </Button>
        </div>

        <p className="muted small" style={{ margin: 0 }}>
          {mode === "move"
            ? "Safely copies the entire relationship brain (database, people, journals, config) to a new directory or external drive. A safety backup is created first."
            : "Points the app to an existing valid People Relationships Data Root. The location will be audited before switching."}
        </p>

        <div>
          <label className="small muted" style={{ display: "block", marginBottom: "4px" }}>
            Current Location:
          </label>
          <input
            type="text"
            readOnly
            value={activeRoot}
            style={{
              width: "100%",
              padding: "6px 10px",
              borderRadius: "6px",
              border: "1px solid #ccc",
              background: "#f5f5f5",
              fontSize: "12px",
            }}
          />
        </div>

        <div>
          <label className="small muted" style={{ display: "block", marginBottom: "4px" }}>
            {mode === "move" ? "Destination Directory Path:" : "Existing Data Root Path:"}
          </label>
          <input
            type="text"
            placeholder={mode === "move" ? "e.g. D:\\Personal\\People Relationships Data" : "e.g. D:\\Personal\\People Relationships Data"}
            value={targetPath}
            onChange={(e) => setTargetPath(e.target.value)}
            disabled={busy}
            style={{
              width: "100%",
              padding: "8px 10px",
              borderRadius: "6px",
              border: "1px solid #999",
              fontSize: "13px",
            }}
          />
        </div>

        <ErrorNote error={error} />
        {info && <div className="info-note">{info}</div>}

        <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "6px" }}>
          <Button kind="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button
            kind="primary"
            disabled={busy || !targetPath.trim()}
            onClick={() => void handleSubmit()}
          >
            {busy ? "Processing…" : mode === "move" ? "Move Data Root" : "Switch Data Root"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
