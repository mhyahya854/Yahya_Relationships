import { useEffect, useRef, useState } from "react";
import { Button, ErrorNote, Modal } from "../../../components/ui";
import { dataRootApi } from "../api";
import type { DataRootCandidate } from "../types";

export function ChangeDataRootDialog({
  activeRoot,
  onClose,
}: {
  activeRoot: string;
  onClose: () => void;
}) {
  const [mode, setMode] = useState<"move" | "switch">("move");
  const [targetPath, setTargetPath] = useState("");
  const [candidate, setCandidate] = useState<DataRootCandidate | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [complete, setComplete] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { inputRef.current?.focus(); }, [mode]);

  async function browse() {
    if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window)) return;
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      const chosen = await invoke<string | null>("pick_folder");
      if (chosen) { setTargetPath(chosen); setCandidate(null); }
    } catch (caught) { setError(caught); }
  }

  async function inspect() {
    if (!targetPath.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const inspected = await dataRootApi.inspect(targetPath.trim());
      if (mode === "move" && inspected.exists && !inspected.is_empty) {
        throw new Error("Move requires a new location or an existing empty folder.");
      }
      setCandidate(inspected);
    } catch (caught) { setError(caught); } finally { setBusy(false); }
  }

  async function confirm() {
    if (!candidate) return;
    setBusy(true);
    setError(null);
    try {
      if (mode === "move") {
        const result = await dataRootApi.move(targetPath.trim());
        setComplete(`Data is now active at ${result.new_root}. Your previous location was left unchanged as an additional safety copy.`);
      } else {
        await dataRootApi.switch(targetPath.trim());
        setComplete("The selected existing Data Root is now active. No data was copied.");
      }
    } catch (caught) { setError(caught); } finally { setBusy(false); }
  }

  const confirmAllowed = candidate && (mode === "move" ? (!candidate.exists || candidate.is_empty) : candidate.can_switch);
  return (
    <Modal title="Change Data Location" onClose={busy ? () => undefined : onClose} wide closeOnEscape={!busy}>
      <div aria-busy={busy} style={{ display: "grid", gap: 14 }}>
        <div role="tablist" aria-label="Data location action" style={{ display: "flex", gap: 8 }}>
          <Button kind={mode === "move" ? "primary" : "default"} disabled={busy} onClick={() => { setMode("move"); setCandidate(null); setComplete(null); }}>Move Current Data</Button>
          <Button kind={mode === "switch" ? "primary" : "default"} disabled={busy} onClick={() => { setMode("switch"); setCandidate(null); setComplete(null); }}>Use Existing Data Root</Button>
        </div>
        <p className="muted small" style={{ margin: 0 }}>
          {mode === "move"
            ? "Copies only the current runtime Data Root, verifies every file, and makes the verified copy active. The old location is retained."
            : "Validates another existing Data Root and makes it active. Current data is not copied."}
        </p>
        <div className="small" style={{ overflowWrap: "anywhere" }}><strong>Current location:</strong> {activeRoot}</div>
        <div><label htmlFor="change-root-path" className="small">{mode === "move" ? "New destination" : "Existing Data Root"}</label><div style={{ display: "flex", gap: 8 }}><input ref={inputRef} id="change-root-path" value={targetPath} disabled={busy} onChange={(event) => { setTargetPath(event.target.value); setCandidate(null); }} placeholder="Choose a folder or enter its path" style={{ flex: 1, minWidth: 0, padding: "8px 10px" }} /><Button disabled={busy} onClick={() => void browse()} title="Browse for a folder">Browse…</Button></div></div>
        <Button kind="primary" disabled={busy || !targetPath.trim()} onClick={() => void inspect()}>{mode === "move" ? "Review Move" : "Inspect Data Root"}</Button>
        {busy && <div role="status" className="info-note">Checking and verifying…</div>}
        <ErrorNote error={error} />
        {candidate && (
          <section aria-label="Data Root change summary" className="info-note" style={{ overflowWrap: "anywhere" }}>
            <strong>{mode === "move" ? "Move summary" : `Candidate: ${candidate.state.replace(/_/g, " ")}`}</strong>
            <div>{candidate.path}</div>
            {mode === "switch" && <div>People: {candidate.person_count} · Journals: {candidate.journal_count} · Schema: {candidate.schema_version ?? "unknown"} · {candidate.read_only ? "Read-only" : "Writable"}</div>}
            {mode === "move" && <div>The runtime Database and Backups will be copied exactly. Source code and Documentation are excluded. The old location will remain.</div>}
          </section>
        )}
        {confirmAllowed && !complete && <Button kind="primary" disabled={busy} onClick={() => void confirm()}>{mode === "move" ? "Confirm Move Current Data" : "Confirm Use This Data Root"}</Button>}
        {complete && <div role="status" className="info-note">{complete}<div style={{ marginTop: 10 }}><Button kind="primary" onClick={() => window.location.reload()}>Reload and Continue</Button></div></div>}
        <div style={{ display: "flex", justifyContent: "flex-end" }}><Button kind="ghost" disabled={busy} onClick={onClose}>Cancel</Button></div>
      </div>
    </Modal>
  );
}
