import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../../api";
import { Markdown } from "../../markdown";
import type { Journal, Person } from "../../types";
import { Button, ErrorNote, Icon } from "../../components/ui";

type Mode = "view" | "edit" | "preview";

function sameRevision(a: Journal | null, b: Journal): boolean {
  return Boolean(
    a &&
      a.exists === b.exists &&
      a.sha256 === b.sha256,
  );
}

export function JournalEditor({
  person,
  initialJournal,
  onDirtyChange,
}: {
  person: Person;
  initialJournal?: Journal;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const [journal, setJournal] = useState<Journal | null>(initialJournal ?? null);
  const [draft, setDraft] = useState(initialJournal?.content ?? "");
  const [mode, setMode] = useState<Mode>("view");
  const [error, setError] = useState<unknown>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [diskVersion, setDiskVersion] = useState<Journal | null>(null);
  const [conflictOpen, setConflictOpen] = useState(false);
  const [cancelGuardOpen, setCancelGuardOpen] = useState(false);
  const [appendOpen, setAppendOpen] = useState(false);
  const [appendText, setAppendText] = useState("");
  const [appendHeading, setAppendHeading] = useState("");
  const [appendError, setAppendError] = useState<string | null>(null);
  const [readOnly, setReadOnly] = useState(false);
  const [maintenance, setMaintenance] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const dirty = Boolean(journal && draft !== journal.content);
  const changedOnDisk = Boolean(diskVersion && !sameRevision(journal, diskVersion));
  const writesBlocked = readOnly || Boolean(maintenance);

  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);

  const loadStorageStatus = useCallback(async () => {
    try {
      const status = await api.dataRoot.status();
      setReadOnly(status.read_only);
      setMaintenance(
        status.maintenance_locked
          ? status.maintenance_operation || "Maintenance"
          : null,
      );
    } catch {
      // Journal reads still provide the authoritative availability signal.
    }
  }, []);

  const load = useCallback(
    async (source: "open" | "reload" | "sync" = "reload") => {
      try {
        const result = await api.journals.get(person.id);
        setError(null);
        if (dirty && journal) {
          if (!sameRevision(journal, result)) {
            setDiskVersion(result);
            if (source === "reload") setConflictOpen(true);
            setInfo("Changed on disk — your unsaved draft is preserved.");
          }
          return;
        }
        setJournal(result);
        setDraft(result.content);
        setDiskVersion(null);
        setConflictOpen(false);
        if (source === "reload") setInfo("Reloaded from journal.md");
      } catch (err) {
        setError(err);
      }
    },
    [dirty, journal, person.id],
  );

  useEffect(() => {
    setJournal(initialJournal ?? null);
    setDraft(initialJournal?.content ?? "");
    setMode("view");
    setDiskVersion(null);
    setConflictOpen(false);
    void load("open");
    void loadStorageStatus();
    // The person identity is the reset boundary; later refreshes preserve drafts.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [person.id]);

  useEffect(() => {
    const sync = () => {
      void load("sync");
      void loadStorageStatus();
    };
    window.addEventListener("focus", sync);
    const timer = window.setInterval(sync, 4000);
    return () => {
      window.removeEventListener("focus", sync);
      window.clearInterval(timer);
    };
  }, [load, loadStorageStatus]);

  useEffect(() => {
    if (!info) return;
    const timer = window.setTimeout(() => setInfo(null), 3000);
    return () => window.clearTimeout(timer);
  }, [info]);

  async function save(force = false) {
    if (!journal || writesBlocked || busy) return;
    setBusy(true);
    try {
      const result = await api.journals.save(person.id, draft, {
        exists: journal.exists,
        modified_ns: journal.modified_ns,
        sha256: journal.sha256,
        force,
      });
      setJournal(result);
      setDraft(result.content);
      setDiskVersion(null);
      setConflictOpen(false);
      setMode("view");
      setInfo(force ? "Disk version overwritten with your draft." : "Saved to journal.md");
      setError(null);
    } catch (err) {
      if (err instanceof ApiError && err.code === "JOURNAL_CONFLICT") {
        try {
          const current = await api.journals.get(person.id);
          setDiskVersion(current);
        } catch {
          const details = err.details;
          setDiskVersion({
            person_id: person.id,
            path: String(details.path ?? journal.path),
            content: String(details.current_content ?? ""),
            exists: Boolean(details.current_exists),
            sha256: (details.current_sha256 as string | null) ?? null,
            modified_ns: (details.current_modified_ns as string | null) ?? null,
          });
        }
        setConflictOpen(true);
        setInfo("Changed on disk — your unsaved draft is preserved.");
      } else {
        setError(err);
        if (err instanceof ApiError && err.code === "DATA_ROOT_READ_ONLY") {
          setReadOnly(true);
        }
      }
    } finally {
      setBusy(false);
    }
  }

  function useDiskVersion() {
    if (!diskVersion) return;
    setJournal(diskVersion);
    setDraft(diskVersion.content);
    setDiskVersion(null);
    setConflictOpen(false);
    setMode("view");
    setInfo("Using the current disk version.");
  }

  function requestCancel() {
    if (dirty) setCancelGuardOpen(true);
    else setMode("view");
  }

  function discardDraft() {
    if (journal) setDraft(journal.content);
    setDiskVersion(null);
    setConflictOpen(false);
    setCancelGuardOpen(false);
    setMode("view");
  }

  async function appendEntry() {
    const text = appendText.trim();
    if (!text) {
      setAppendError("Journal entry text is required.");
      return;
    }
    setBusy(true);
    try {
      const result = await api.journals.append(
        person.id,
        text,
        appendHeading.trim() || undefined,
      );
      setJournal(result);
      setDraft(result.content);
      setDiskVersion(null);
      setAppendOpen(false);
      setAppendText("");
      setAppendHeading("");
      setAppendError(null);
      setInfo("Entry appended to journal.md");
      setError(null);
    } catch (err) {
      setError(err);
      if (err instanceof ApiError && err.code === "DATA_ROOT_READ_ONLY") {
        setReadOnly(true);
      }
    } finally {
      setBusy(false);
    }
  }

  const status = changedOnDisk
    ? "Changed on disk"
    : dirty
      ? "Unsaved"
      : "Saved";
  const canonicalStatus = useMemo(() => {
    if (!journal) return "Loading canonical journal…";
    if (!journal.exists) return "Canonical journal missing";
    if (!journal.content) return "Canonical journal exists and is empty";
    return "Canonical journal loaded";
  }, [journal]);

  if (!journal) {
    return <div className="muted">Loading journal.md…</div>;
  }

  return (
    <section className="journal-experience" aria-label={`Journal for ${person.name}`}>
      <div className="journal-meta">
        <div>
          <strong>{person.name}</strong>
          <span className="muted tiny"> · {canonicalStatus}</span>
        </div>
        <span className={`journal-status ${changedOnDisk ? "changed" : dirty ? "unsaved" : "saved"}`}>
          {status}
        </span>
      </div>

      <div className="journal-toolbar" role="toolbar" aria-label="Journal actions">
        <div className="journal-mode-switch" aria-label="Journal mode">
          <Button className="journal-mode" ariaPressed={mode === "view"} onClick={() => setMode("view")} disabled={mode === "view"}><Icon name="view" />View</Button>
          <Button className="journal-mode" ariaPressed={mode === "edit"} onClick={() => setMode("edit")} disabled={mode === "edit" || writesBlocked}><Icon name="edit" />Edit</Button>
          <Button className="journal-mode" ariaPressed={mode === "preview"} onClick={() => setMode("preview")} disabled={mode === "preview" || !dirty}><Icon name="profile" />Preview</Button>
        </div>
        <div className="journal-primary-actions">
          <Button kind="primary" onClick={() => void save()} disabled={!dirty || writesBlocked || busy}>Save</Button>
          <Button onClick={requestCancel} disabled={mode === "view"}>Cancel</Button>
        </div>
        <div className="journal-secondary-actions">
          <Button onClick={() => journal && setDraft(journal.content)} disabled={!dirty}>Revert</Button>
          <Button
            onClick={() => setAppendOpen(true)}
            disabled={dirty || writesBlocked || busy}
            title={dirty ? "Save or discard the current draft before Quick Append." : undefined}
          >
            Quick Append
          </Button>
          <Button className="icon-button" ariaLabel="Reload journal" title="Reload journal" onClick={() => void load("reload")} disabled={busy}><Icon name="reload" /><span className="sr-only">Reload</span></Button>
        </div>
      </div>

      {writesBlocked && (
        <div className="journal-blocked" role="status">
          {readOnly
            ? "This Data Root is read-only. Viewing, previewing, and reloading remain available; Journal writes are disabled."
            : `Journal writes are temporarily disabled during ${maintenance}.`}
        </div>
      )}
      {!journal.exists && (
        <div className="journal-missing-warning" role="status">
          journal.md is missing. This read did not create it; the first explicit Save or Quick Append will.
        </div>
      )}
      {changedOnDisk && !conflictOpen && (
        <div className="journal-changed-warning" role="status">
          Changed on disk. Your local draft is still intact. Reload to compare and resolve.
        </div>
      )}
      <ErrorNote error={error} />
      {info && <div className="info-note" role="status">{info}</div>}

      {mode === "edit" ? (
        <label className="journal-editor-label">
          <span className="sr-only">Journal Markdown</span>
          <textarea
            className="journal-editor"
            aria-label="Journal Markdown"
            dir="auto"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
                event.preventDefault();
                void save();
              } else if (event.key === "Escape") {
                event.preventDefault();
                event.stopPropagation();
                requestCancel();
              }
            }}
            spellCheck={false}
          />
        </label>
      ) : mode === "preview" ? (
        <div className="journal-view journal-preview" aria-label="Journal preview">
          <Markdown text={draft} />
        </div>
      ) : journal.content ? (
        <div className="journal-view" aria-label="Journal content">
          <Markdown text={journal.content} />
        </div>
      ) : (
        <div className="empty-state">No journal prose recorded yet.</div>
      )}

      <details className="technical-disclosure journal-hint">
        <summary>Journal details</summary>
        <div className="muted tiny">
          Canonical source: <code>journal.md</code> · UTF-8 · LF · revision {journal.sha256?.slice(0, 12) ?? "missing"}
        </div>
      </details>

      {appendOpen && (
        <div
          className="journal-inline-dialog"
          role="dialog"
          aria-modal="true"
          aria-label="Quick Append"
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.preventDefault();
              event.stopPropagation();
            }
          }}
        >
          <h3>Quick Append</h3>
          <label>
            Heading <span className="muted tiny">(optional; defaults to today)</span>
            <input
              aria-label="Quick Append heading"
              value={appendHeading}
              onChange={(event) => setAppendHeading(event.target.value)}
              placeholder="YYYY-MM-DD or a short heading"
            />
          </label>
          <label>
            Entry
            <textarea
              aria-label="Quick Append entry"
              dir="auto"
              value={appendText}
              onChange={(event) => {
                setAppendText(event.target.value);
                setAppendError(null);
              }}
              autoFocus
            />
          </label>
          {appendError && <div className="error-note">{appendError}</div>}
          <div className="journal-dialog-actions">
            <Button onClick={() => setAppendOpen(false)}>Cancel</Button>
            <Button kind="primary" onClick={() => void appendEntry()} disabled={busy}>Append</Button>
          </div>
        </div>
      )}

      {cancelGuardOpen && (
        <div className="journal-inline-dialog" role="alertdialog" aria-modal="true" aria-label="Unsaved Journal changes">
          <h3>Unsaved Journal changes</h3>
          <p>Your draft has not been saved to journal.md.</p>
          <div className="journal-dialog-actions">
            <Button kind="primary" onClick={() => setCancelGuardOpen(false)}>Keep Editing</Button>
            <Button kind="danger" onClick={discardDraft}>Discard</Button>
          </div>
        </div>
      )}

      {conflictOpen && diskVersion && (
        <div className="journal-conflict" role="alertdialog" aria-modal="true" aria-label="Journal conflict">
          <h3>Journal changed on disk</h3>
          <p>Your draft was preserved. Choose explicitly; no automatic merge or overwrite will occur.</p>
          <div className="journal-conflict-grid">
            <label>
              My local draft
              <textarea readOnly dir="auto" value={draft} aria-label="My local draft" />
            </label>
            <label>
              Disk version {diskVersion.exists ? "" : "(file deleted)"}
              <textarea readOnly dir="auto" value={diskVersion.content} aria-label="Disk version" />
            </label>
          </div>
          <div className="journal-dialog-actions">
            <Button onClick={() => setConflictOpen(false)}>Keep Editing</Button>
            <Button onClick={useDiskVersion}>Use Disk Version</Button>
            <Button kind="danger" onClick={() => void save(true)} disabled={writesBlocked || busy}>
              Overwrite Disk With My Draft
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
