import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { Button, ErrorNote, Modal } from "../components/ui";

type RawProposal = {
  proposal_state: "READY" | "BLOCKED_BY_FUTURE_PHASE" | "NEEDS_USER_INPUT" | "CONFLICT" | "UNKNOWN";
  destination_relative_path: string | null;
  reason: string;
  stale: number;
  created_at: string;
};

type RawItem = {
  id: string;
  original_relative_path: string;
  current_relative_path: string | null;
  final_relative_path: string | null;
  entry_kind: string;
  classification: string;
  classification_source: string;
  classification_confidence: number | null;
  size_bytes: number | null;
  sha256: string | null;
  availability_state: string;
  processing_state: string;
  analysis_status: string;
  duplicate_group_id: string | null;
  duplicate_count: number;
  proposal: RawProposal | null;
  paths?: Array<{ relative_path: string; path_event: string; observed_at: string }>;
  decisions?: Array<{ decision: string; note: string | null; created_at: string }>;
  events?: Array<{ event_type: string; created_at: string; payload_json: string }>;
  duplicates?: Array<{ id: string; current_relative_path: string | null; availability_state: string }>;
  archive_inventory?: { safety_status: string; member_count: number | null; uncompressed_bytes: number | null; inventory_json: string } | null;
};

type RawResponse = {
  items: RawItem[];
  counts: Record<string, number>;
  latest_run: { status: string; completed_at: string | null; summary_json: string } | null;
  raw_exists: boolean;
};

const FILTERS = [
  ["all", "All"], ["needs_review", "Needs Review"], ["duplicates", "Duplicates"],
  ["unknown", "Unknown"], ["blocked", "Blocked"], ["errors", "Errors"],
  ["moved", "Moved"], ["missing", "Missing"],
] as const;

const CLASSES = ["image", "video", "audio", "document", "archive", "social_export_candidate", "location_export_candidate", "phone_backup_candidate", "folder/container", "unknown"];

function formatBytes(bytes: number | null) {
  if (bytes == null) return "Unknown size";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function label(value: string | null | undefined) {
  return (value ?? "Unknown").replace(/_/g, " ").replace(/\b\w/g, (letter: string) => letter.toUpperCase());
}

export function RawView() {
  const [data, setData] = useState<RawResponse | null>(null);
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<RawItem | null>(null);
  const [scanBusy, setScanBusy] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [approvalOpen, setApprovalOpen] = useState(false);
  const [classification, setClassification] = useState("unknown");
  const [destination, setDestination] = useState("");
  const [note, setNote] = useState("");

  const load = useCallback(async (nextFilter = filter, nextQuery = query) => {
    try {
      const result = await api.raw.list(nextFilter, nextQuery) as RawResponse;
      setData(result);
      setError(null);
      return result;
    } catch (err) {
      setError(err);
      return null;
    }
  }, [filter, query]);

  useEffect(() => { void load(); }, [load]);

  const select = useCallback(async (item: RawItem) => {
    try {
      const result = await api.raw.get(item.id) as { item: RawItem };
      setSelected(result.item);
      setClassification(result.item.classification);
      setDestination(result.item.proposal?.destination_relative_path ?? "");
      setNote("");
    } catch (err) { setError(err); }
  }, []);

  async function scan() {
    setScanBusy(true); setInfo(null); setError(null);
    try {
      const result = await api.raw.scan() as { summary: { items: number; errors: number }; status: string };
      setInfo(`Raw scan ${label(result.status)}: ${result.summary.items} entries observed${result.summary.errors ? `; ${result.summary.errors} need attention` : ""}.`);
      await load();
    } catch (err) { setError(err); } finally { setScanBusy(false); }
  }

  async function refreshSelected() {
    if (!selected) return;
    const result = await api.raw.get(selected.id) as { item: RawItem };
    setSelected(result.item);
    await load();
  }

  async function correct() {
    if (!selected) return;
    setActionBusy(true); setError(null);
    try {
      await api.raw.correct(selected.id, {
        classification,
        destination_relative_path: destination.trim() || undefined,
        note: note.trim() || undefined,
      });
      setInfo("Correction recorded. Machine detection remains distinct from this human decision.");
      await refreshSelected();
    } catch (err) { setError(err); } finally { setActionBusy(false); }
  }

  async function decide(decision: "APPROVED" | "REJECTED" | "DEFERRED") {
    if (!selected) return;
    setActionBusy(true); setError(null);
    try {
      await api.raw.decision(selected.id, decision, note.trim() || undefined);
      setApprovalOpen(false);
      setInfo(`${label(decision)} decision recorded.`);
      await refreshSelected();
    } catch (err) { setError(err); } finally { setActionBusy(false); }
  }

  async function move() {
    if (!selected) return;
    setActionBusy(true); setError(null);
    try {
      await api.raw.move(selected.id);
      setInfo("Destination bytes were verified before the source left Raw; the move was recorded in processing history.");
      await refreshSelected();
    } catch (err) { setError(err); } finally { setActionBusy(false); }
  }

  async function rehash() {
    if (!selected) return;
    setActionBusy(true); setError(null);
    try {
      await api.raw.rehash(selected.id);
      setInfo("Rescan and rehash completed without modifying the Raw source.");
      await refreshSelected();
    } catch (err) { setError(err); } finally { setActionBusy(false); }
  }

  const selectedCanApprove = selected?.proposal?.proposal_state === "READY" && !selected.proposal.stale && selected.processing_state !== "MOVED";
  const selectedCanMove = selected?.processing_state === "APPROVED" && selected?.proposal?.proposal_state === "READY" && !selected.proposal.stale;
  const rows = data?.items ?? [];
  const status = data?.latest_run ? `${label(data.latest_run.status)}${data.latest_run.completed_at ? ` · ${data.latest_run.completed_at}` : ""}` : "Not scanned yet";
  const blockedCopy = useMemo(() => selected?.proposal?.proposal_state === "BLOCKED_BY_FUTURE_PHASE"
    ? "This type needs a later domain processor. It remains in Raw and cannot be approved for a canonical move in Phase 12."
    : null, [selected]);

  return (
    <div className="view raw-view">
      <div className="view-head">
        <div>
          <h1>Raw Intake</h1>
          <p className="muted">Read-only discovery and human review for unorganized source material. Nothing leaves Raw without a current proposal and explicit approval.</p>
        </div>
        <Button kind="primary" disabled={scanBusy} onClick={() => void scan()}>{scanBusy ? "Scanning…" : "Scan / Rescan Raw"}</Button>
      </div>

      <div className="info-note raw-safety-note"><strong>Source safety:</strong> scanning never renames, unpacks, modifies, moves, or deletes Raw material. Archive inspection is metadata-only; automatic duplicate deletion is not implemented.</div>
      <ErrorNote error={error} />
      {info && <div className="info-note">{info}</div>}

      <div className="raw-summary" aria-label="Raw intake status">
        <div><span className="muted tiny">Last scan</span><strong>{status}</strong></div>
        <div><span className="muted tiny">Raw area</span><strong>{data?.raw_exists ? "Available" : "Created on first scan"}</strong></div>
        <div><span className="muted tiny">Items</span><strong>{data?.counts.all ?? 0}</strong></div>
        <div><span className="muted tiny">Needs review</span><strong>{data?.counts.needs_review ?? 0}</strong></div>
      </div>

      <div className="raw-toolbar">
        <div className="tabs raw-filters" aria-label="Raw filters">
          {FILTERS.map(([id, text]) => <Button key={id} kind="ghost" className={`chip-button ${filter === id ? "active" : ""}`} ariaPressed={filter === id} onClick={() => { setFilter(id); void load(id, query); }}>{text} ({data?.counts[id] ?? 0})</Button>)}
        </div>
        <input className="raw-search" value={query} onChange={(event) => { const value = event.target.value; setQuery(value); void load(filter, value); }} placeholder="Search Raw paths or types" aria-label="Search Raw items" />
      </div>

      {rows.length === 0 ? (
        <div className="empty-state large raw-empty"><strong>No Raw items match this view.</strong><span>Place material in <code>Raw/</code>, then run a read-only scan.</span></div>
      ) : (
        <div className="raw-workspace">
          <div className="raw-table-wrap">
            <table className="raw-table">
              <thead><tr><th>Source</th><th>Type</th><th>Hash / duplicate</th><th>Review</th><th>Proposal</th></tr></thead>
              <tbody>{rows.map((item) => (
                <tr key={item.id} className={selected?.id === item.id ? "selected" : ""} onClick={() => void select(item)} tabIndex={0} onKeyDown={(event) => { if (event.key === "Enter") void select(item); }}>
                  <td><strong>{item.current_relative_path ?? item.final_relative_path ?? item.original_relative_path}</strong><span className="muted tiny">{formatBytes(item.size_bytes)} · {label(item.availability_state)}</span></td>
                  <td><span className="chip">{label(item.classification)}</span><span className="muted tiny">{item.classification_source === "human" ? "Human corrected" : "Deterministic suggestion"}</span></td>
                  <td><span className="raw-hash">{item.sha256 ? `${item.sha256.slice(0, 12)}…` : "Not hashed"}</span>{item.duplicate_count > 1 && <span className="chip raw-duplicate">{item.duplicate_count} exact copies</span>}</td>
                  <td><span className={`raw-status raw-${item.processing_state.toLowerCase()}`}>{label(item.processing_state)}</span></td>
                  <td><span className="muted small">{label(item.proposal?.proposal_state)}</span></td>
                </tr>
              ))}</tbody>
            </table>
          </div>

          <aside className="raw-detail" aria-label="Raw item detail">
            {!selected ? <div className="empty-state">Select an item to inspect its source, analysis, provenance, duplicate links, proposal, and review actions.</div> : <>
              <div className="raw-detail-head"><div><span className="muted tiny">Raw item</span><h2>{selected.current_relative_path ?? selected.final_relative_path ?? selected.original_relative_path}</h2></div><Button kind="ghost" onClick={() => setSelected(null)}>Close</Button></div>
              <section><h3>Source</h3><dl><dt>Original</dt><dd>{selected.original_relative_path}</dd><dt>Current</dt><dd>{selected.current_relative_path ?? "No longer in Raw"}</dd><dt>Size</dt><dd>{formatBytes(selected.size_bytes)}</dd><dt>SHA-256</dt><dd className="raw-digest">{selected.sha256 ?? "Not available"}</dd><dt>Availability</dt><dd>{label(selected.availability_state)}</dd></dl></section>
              <section><h3>Analysis</h3><p><span className="chip">{label(selected.classification)}</span> <span className="muted small">{selected.classification_source === "human" ? "Human-confirmed correction" : "Deterministic detection, not a confirmed fact"}</span></p><p className="muted small">Future processors: {selected.analysis_status.replace(/_/g, " ")}. No OCR, transcript, identity, face, or location fact has been generated.</p>{blockedCopy && <div className="info-note">{blockedCopy}</div>}</section>
              <section><h3>Duplicates</h3>{selected.duplicate_count > 1 ? <><p className="muted small">Exact SHA-256 group: {selected.duplicate_count} separately retained source records. No deletion is automatic.</p><ul>{selected.duplicates?.map((duplicate) => <li key={duplicate.id}>{duplicate.current_relative_path ?? duplicate.id} · {label(duplicate.availability_state)}</li>)}</ul></> : <p className="muted small">No other Raw record currently has this exact verified hash.</p>}</section>
              <section><h3>Proposal</h3><p><strong>{label(selected.proposal?.proposal_state)}</strong></p><p className="muted small">{selected.proposal?.reason ?? "No current proposal."}</p>{selected.proposal?.destination_relative_path && <code>{selected.proposal.destination_relative_path}</code>}{selected.proposal?.stale ? <div className="error-note">This proposal is stale and cannot be approved.</div> : null}</section>
              <section><h3>Human correction</h3><label>Classification<select value={classification} disabled={actionBusy} onChange={(event) => setClassification(event.target.value)}>{CLASSES.map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label><label>Authorized generic source destination (optional)<input value={destination} disabled={actionBusy} onChange={(event) => setDestination(event.target.value)} placeholder="Database/Sources/batch/filename.ext" /></label><p className="muted tiny">Only a manually selected path under <code>Database/Sources/</code> can become READY in Phase 12. All media/event/social/location destinations remain blocked for later phases.</p><label>Review note<textarea value={note} disabled={actionBusy} onChange={(event) => setNote(event.target.value)} rows={2} /></label><Button kind="ghost" disabled={actionBusy} onClick={() => void correct()}>Save correction</Button></section>
              <section><h3>Decision</h3><div className="raw-actions"><Button kind="primary" disabled={!selectedCanApprove || actionBusy} onClick={() => setApprovalOpen(true)}>Approve proposal</Button><Button kind="ghost" disabled={actionBusy || selected.processing_state === "MOVED"} onClick={() => void decide("DEFERRED")}>Defer</Button><Button kind="danger" disabled={actionBusy || selected.processing_state === "MOVED"} onClick={() => void decide("REJECTED")}>Reject</Button><Button kind="ghost" disabled={actionBusy || !selected.current_relative_path} onClick={() => void rehash()}>Rehash / rescan</Button></div>{selectedCanMove && <div className="raw-move-box"><strong>Approved, ready to move</strong><p className="muted small">The source leaves Raw only after a verified copy reaches the exact destination shown above. Existing destinations are never overwritten.</p><Button kind="primary" disabled={actionBusy} onClick={() => void move()}>Move approved file</Button></div>}</section>
              <section><h3>Provenance & history</h3><ul className="raw-event-list">{selected.events?.slice(0, 8).map((event) => <li key={`${event.event_type}-${event.created_at}`}><strong>{label(event.event_type)}</strong><span>{event.created_at}</span></li>)}</ul><p className="muted tiny">Full append-oriented history: <code>Database/raw_processing_history.md</code></p></section>
            </>}
          </aside>
        </div>
      )}

      {approvalOpen && selected && <Modal title="Approve Raw proposal" onClose={() => !actionBusy && setApprovalOpen(false)}>
        <p>This approval permits one later, explicit move. It does not move anything yet.</p>
        <dl className="raw-approval-summary"><dt>Raw source</dt><dd>{selected.current_relative_path}</dd><dt>Exact destination</dt><dd>{selected.proposal?.destination_relative_path}</dd><dt>What changes</dt><dd>After you separately choose “Move approved file,” the original leaves Raw only after a byte-identical destination copy is verified.</dd><dt>Destructive deletion</dt><dd>No duplicate deletion is included in this flow.</dd></dl>
        <div className="raw-actions"><Button kind="ghost" disabled={actionBusy} onClick={() => setApprovalOpen(false)}>Cancel</Button><Button kind="primary" disabled={actionBusy} onClick={() => void decide("APPROVED")}>{actionBusy ? "Checking source…" : "Record approval"}</Button></div>
      </Modal>}
    </div>
  );
}
