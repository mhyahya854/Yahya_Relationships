import { useEffect, useRef, useState } from "react";
import { Button, ErrorNote } from "../../../components/ui";
import { dataRootApi } from "../api";
import type { BackupInspection, DataRootCandidate, DataRootState, ValidationIssue } from "../types";

type Flow = "existing" | "restore" | "create";

async function pickFolderNative(): Promise<string | null> {
  if (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window) {
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      return await invoke<string | null>("pick_folder");
    } catch (error) {
      console.warn("Native folder picker unavailable; manual path entry remains available.", error);
    }
  }
  return null;
}

function PathField({ id, label, value, onChange, disabled }: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
}) {
  async function browse() {
    const chosen = await pickFolderNative();
    if (chosen) onChange(chosen);
  }
  return (
    <div style={{ textAlign: "left" }}>
      <label htmlFor={id} className="small" style={{ display: "block", marginBottom: 5 }}>{label}</label>
      <div style={{ display: "flex", gap: 8 }}>
        <input
          id={id}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          disabled={disabled}
          placeholder="Choose a folder or enter its path"
          style={{ flex: 1, minWidth: 0, padding: "8px 10px" }}
        />
        <Button kind="default" disabled={disabled} onClick={() => void browse()} title={`Browse for ${label}`}>
          Browse…
        </Button>
      </div>
    </div>
  );
}

function CandidateSummary({ candidate }: { candidate: DataRootCandidate }) {
  return (
    <section aria-label="Data Root candidate summary" className="info-note" style={{ textAlign: "left" }}>
      <strong>Candidate: {candidate.state.replace(/_/g, " ")}</strong>
      <div className="small" style={{ overflowWrap: "anywhere" }}>{candidate.path}</div>
      <div className="small">People: {candidate.person_count} · Journals: {candidate.journal_count} · Schema: {candidate.schema_version ?? "unknown"}</div>
      <div className="small">Data Root format: {candidate.data_root_format_version ?? "legacy compatible"} · {candidate.read_only ? "Read-only" : "Writable"}</div>
      {candidate.root_id && <details className="technical-disclosure"><summary>Technical identity</summary><div className="small">Root identity: {candidate.root_id}</div></details>}
      {candidate.issues.length > 0 && (
        <ul>{candidate.issues.map((issue) => <li key={`${issue.code}-${issue.message}`}>{issue.code}: {issue.message}</li>)}</ul>
      )}
    </section>
  );
}

function IssueList({ issues }: { issues: ValidationIssue[] }) {
  if (!issues.length) return null;
  return (
    <section aria-label="Data Root issues" style={{ textAlign: "left", marginTop: 14 }}>
      <strong>What needs attention</strong>
      <ul>{issues.map((issue) => <li key={`${issue.code}-${issue.message}`}><strong>{issue.code}</strong>: {issue.message}</li>)}</ul>
    </section>
  );
}

export function RootUnavailableView({
  state,
  lastLocation,
  issues,
  onRecovered,
}: {
  state: DataRootState;
  lastLocation?: string | null;
  issues: ValidationIssue[];
  onRecovered: () => void;
}) {
  const [flow, setFlow] = useState<Flow | null>(null);
  const [candidatePath, setCandidatePath] = useState("");
  const [destinationPath, setDestinationPath] = useState("");
  const [ownerName, setOwnerName] = useState("");
  const [ownerGender, setOwnerGender] = useState("");
  const [candidate, setCandidate] = useState<DataRootCandidate | null>(null);
  const [backup, setBackup] = useState<BackupInspection | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [completed, setCompleted] = useState<string | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => { headingRef.current?.focus(); }, [flow]);

  function reset(next: Flow | null) {
    setFlow(next);
    setCandidate(null);
    setBackup(null);
    setError(null);
    setCompleted(null);
  }

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try { await action(); } catch (caught) { setError(caught); } finally { setBusy(false); }
  }

  async function retry() {
    await run(async () => {
      const status = await dataRootApi.getStatus();
      if (["HEALTHY", "READ_ONLY", "REPAIRABLE"].includes(status.state)) onRecovered();
      else throw new Error("The saved Data Root is still unavailable or invalid.");
    });
  }

  async function inspectExisting() {
    await run(async () => setCandidate(await dataRootApi.inspect(candidatePath.trim())));
  }

  async function reviewDestination() {
    await run(async () => {
      const inspected = await dataRootApi.inspect(destinationPath.trim());
      if (inspected.exists && !inspected.is_empty) throw new Error("Choose a new location or an existing empty folder.");
      setCandidate(inspected);
    });
  }

  async function confirmExisting() {
    if (!candidate?.can_switch) return;
    await run(async () => {
      await dataRootApi.switch(candidate.path);
      setCompleted(candidate.read_only ? "The read-only Data Root is now active." : "The selected Data Root is now active.");
    });
  }

  async function verifyBackup() {
    await run(async () => setBackup(await dataRootApi.inspectBackup(candidatePath.trim())));
  }

  async function confirmRestore() {
    if (!backup?.ok || !candidate || (candidate.exists && !candidate.is_empty)) return;
    await run(async () => {
      await dataRootApi.restoreTo(backup.path, destinationPath.trim());
      setCompleted("The verified backup was restored into the new Data Root.");
    });
  }

  async function confirmCreate() {
    if (!candidate || !ownerName.trim() || (candidate.exists && !candidate.is_empty)) return;
    await run(async () => {
      await dataRootApi.initialize(destinationPath.trim(), ownerName.trim(), ownerGender || undefined);
      setCompleted("Your new Data Root is ready.");
    });
  }

  async function repair() {
    await run(async () => {
      const result = await dataRootApi.repair();
      if (!result.ok) throw new Error("Safe Repair could not resolve this Data Root.");
      onRecovered();
    });
  }

  const isFirstRun = state === "UNCONFIGURED";
  const malformed = issues.some((issue) => issue.code === "BOOTSTRAP_INVALID");
  const title = isFirstRun ? "Welcome to People Relationships" : malformed ? "Data-location setting needs attention" : state === "MISSING" ? "Data location unavailable" : "Data Root needs attention";
  const subtitle = isFirstRun
    ? "Choose an existing Data Root, restore a directory snapshot, or create a fresh Data Root."
    : malformed
      ? "Your saved data-location setting could not be read. No replacement data was created."
      : state === "MISSING"
        ? "The saved location is not currently available. Reconnect it or choose a recovery route."
        : "The saved location exists but is not safe to open normally.";

  return (
    <main className="root-unavailable-view" aria-busy={busy}>
      <div className="root-unavailable-card">
        <h1 ref={headingRef} tabIndex={-1} style={{ marginTop: 0, outline: "none" }}>{flow ? ({ existing: "Use Existing Data Root", restore: "Restore From Backup", create: "Create New Data Root" }[flow]) : title}</h1>
        {!flow && <p className="muted">{subtitle}</p>}
        {!flow && lastLocation && <details className="technical-disclosure info-note" style={{ overflowWrap: "anywhere" }}><summary>Last known location</summary><div>{lastLocation}</div></details>}
        {!flow && <IssueList issues={issues} />}
        <ErrorNote error={error} />
        {busy && <div role="status" className="info-note">Checking and verifying…</div>}
        {completed && (
          <div role="status" className="info-note">
            {completed}
            <div style={{ marginTop: 10 }}><Button kind="primary" onClick={() => window.location.reload()}>Continue</Button></div>
          </div>
        )}

        {!flow && !completed && (
          <div className="recovery-routes">
            {!isFirstRun && <Button kind="primary" disabled={busy} onClick={() => void retry()}>Retry</Button>}
            <Button kind={isFirstRun ? "primary" : "default"} disabled={busy} onClick={() => reset("existing")}>Use Existing Data Root</Button>
            <span className="muted small">Validate another existing Data Root and make it active without copying current data.</span>
            <Button kind="default" disabled={busy} onClick={() => reset("restore")}>Restore From Backup</Button>
            <span className="muted small">Verify a backup snapshot, then restore it into a separate new location.</span>
            <div className={!isFirstRun ? "recovery-route-separated" : undefined}>
              <Button kind="default" disabled={busy} onClick={() => reset("create")}>Create New Data Root</Button>
              <div className="muted small">Start fresh with your name and one initial person record. This does not recover missing data.</div>
            </div>
            {state === "REPAIRABLE" && <Button kind="default" disabled={busy} onClick={() => void repair()}>Run Safe Repair</Button>}
          </div>
        )}

        {flow === "existing" && !completed && (
          <div className="recovery-flow">
            <p className="muted">This does not copy current data. You will review health and counts before switching.</p>
            <PathField id="existing-root-path" label="Existing Data Root" value={candidatePath} onChange={(value) => { setCandidatePath(value); setCandidate(null); }} disabled={busy} />
            <Button kind="primary" disabled={busy || !candidatePath.trim()} onClick={() => void inspectExisting()}>Inspect Data Root</Button>
            {candidate && <CandidateSummary candidate={candidate} />}
            {candidate?.can_switch && <Button kind="primary" disabled={busy} onClick={() => void confirmExisting()}>Confirm Use This Data Root</Button>}
          </div>
        )}

        {flow === "create" && !completed && (
          <div className="recovery-flow">
            <p className="muted">Create a fresh schema-v2 Data Root. Existing non-empty folders are never reused or overwritten.</p>
            <PathField id="new-root-path" label="New Data Root location" value={destinationPath} onChange={(value) => { setDestinationPath(value); setCandidate(null); }} disabled={busy} />
            <div className="recovery-field"><label htmlFor="owner-name" className="small">Your name</label><input className="text-input" id="owner-name" value={ownerName} onChange={(event) => setOwnerName(event.target.value)} disabled={busy} /></div>
            <div className="recovery-field"><label htmlFor="owner-gender" className="small">Gender (optional)</label><select className="select-input" id="owner-gender" value={ownerGender} onChange={(event) => setOwnerGender(event.target.value)} disabled={busy}><option value="">Unspecified</option><option value="unknown">Unknown</option><option value="female">Female</option><option value="male">Male</option></select></div>
            <Button kind="primary" disabled={busy || !destinationPath.trim() || !ownerName.trim()} onClick={() => void reviewDestination()}>Review New Data Root</Button>
            {candidate && <section aria-label="New Data Root summary" className="info-note" style={{ textAlign: "left" }}><strong>Ready to create</strong><div>{destinationPath}</div><div>Initial owner: {ownerName.trim()}</div><div>Schema: 2 · one owner · default perspective</div></section>}
            {candidate && (!candidate.exists || candidate.is_empty) && <Button kind="primary" disabled={busy} onClick={() => void confirmCreate()}>Confirm Create New Data Root</Button>}
          </div>
        )}

        {flow === "restore" && !completed && (
          <div className="recovery-flow">
            <p className="muted">The backup snapshot and the new active Data Root are two separate locations.</p>
            <PathField id="backup-source-path" label="Backup snapshot source" value={candidatePath} onChange={(value) => { setCandidatePath(value); setBackup(null); }} disabled={busy} />
            <Button kind="primary" disabled={busy || !candidatePath.trim()} onClick={() => void verifyBackup()}>Verify Backup</Button>
            {backup && <section aria-label="Backup verification summary" className="info-note" style={{ textAlign: "left" }}><strong>{backup.ok ? "Verified backup" : "Backup verification failed"}</strong><div>{backup.path}</div><div>People: {backup.manifest?.person_count ?? "unknown"} · Journals: {backup.manifest?.journal_count ?? "unknown"} · Schema: {backup.manifest?.sqlite_schema_version ?? "unknown"}</div></section>}
            {backup?.ok && <PathField id="restore-destination-path" label="New Data Root destination" value={destinationPath} onChange={(value) => { setDestinationPath(value); setCandidate(null); }} disabled={busy} />}
            {backup?.ok && <Button kind="primary" disabled={busy || !destinationPath.trim()} onClick={() => void reviewDestination()}>Review Restore</Button>}
            {backup?.ok && candidate && (!candidate.exists || candidate.is_empty) && <section aria-label="Restore summary" className="info-note" style={{ textAlign: "left" }}><strong>Restore summary</strong><div>From: {backup.path}</div><div>To: {destinationPath}</div><div>The source will remain unchanged.</div><Button kind="primary" disabled={busy} onClick={() => void confirmRestore()}>Confirm Restore to New Data Root</Button></section>}
          </div>
        )}

        {flow && !completed && <div style={{ marginTop: 18 }}><Button kind="ghost" disabled={busy} onClick={() => reset(null)}>Back</Button></div>}
      </div>
    </main>
  );
}
