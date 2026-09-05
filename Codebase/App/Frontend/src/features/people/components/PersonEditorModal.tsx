import React, { useEffect, useState } from "react";
import { api } from "../../../api";
import type { DuplicateCandidate, Group, MutationPreviewResult, Person } from "../../../types";

interface Props {
  mode: "add" | "edit" | "delete";
  person?: Person | null;
  groups: Group[];
  onClose: () => void;
  onSaved: (desc: string) => void;
  onOpenExisting?: (personId: string) => void;
}

export const PersonEditorModal: React.FC<Props> = ({
  mode,
  person,
  groups,
  onClose,
  onSaved,
  onOpenExisting,
}) => {
  const [name, setName] = useState(person?.name || "");
  const [aliasesText, setAliasesText] = useState(person?.aliases.join(", ") || "");
  const [gender, setGender] = useState<string>(person?.gender || "unknown");
  const [birthYear, setBirthYear] = useState<string>(person?.birth_year ? String(person.birth_year) : "");
  const [noteEn, setNoteEn] = useState<string>(person?.note_en || "");

  // Multi-group state
  const initialGroupIds = person?.groups.map((g) => g.id) || (groups.length > 0 ? [groups[0].id] : ["family"]);
  const [selectedGroupIds, setSelectedGroupIds] = useState<string[]>(initialGroupIds);
  const initialPrimaryId = person?.groups.find((g) => g.is_primary)?.id || initialGroupIds[0] || "family";
  const [primaryGroupId, setPrimaryGroupId] = useState<string>(initialPrimaryId);

  const [duplicates, setDuplicates] = useState<DuplicateCandidate[]>([]);
  const [allowCreateAnyway, setAllowCreateAnyway] = useState(false);
  const [deletePreview, setDeletePreview] = useState<MutationPreviewResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (mode === "delete" && person) {
      void loadDeletePreview();
    }
  }, [mode, person?.id]);

  useEffect(() => {
    if (mode === "add" && name.trim().length >= 2) {
      const timer = setTimeout(async () => {
        try {
          const aliases = aliasesText.split(",").map((s) => s.trim()).filter(Boolean);
          const res = await api.people.checkDuplicate(name.trim(), aliases);
          setDuplicates(res.candidates);
        } catch {
          setDuplicates([]);
        }
      }, 300);
      return () => clearTimeout(timer);
    } else {
      setDuplicates([]);
    }
  }, [name, aliasesText, mode]);

  const loadDeletePreview = async () => {
    if (!person) return;
    setLoading(true);
    try {
      const preview = await api.mutations.preview("delete_person", { person_id: person.id });
      setDeletePreview(preview);
    } catch (err: unknown) {
      setErrorMsg((err as Error).message || "Failed to calculate deletion impact.");
    } finally {
      setLoading(false);
    }
  };

  const toggleGroup = (gid: string) => {
    if (selectedGroupIds.includes(gid)) {
      if (selectedGroupIds.length === 1) {
        setErrorMsg("A person must belong to at least one group.");
        return;
      }
      const updated = selectedGroupIds.filter((id) => id !== gid);
      setSelectedGroupIds(updated);
      if (primaryGroupId === gid) {
        setPrimaryGroupId(updated[0]);
      }
    } else {
      setErrorMsg(null);
      const updated = [...selectedGroupIds, gid];
      setSelectedGroupIds(updated);
      if (!primaryGroupId) {
        setPrimaryGroupId(gid);
      }
    }
  };

  const handleSaveAdd = async () => {
    const trimmed = name.trim();
    if (!trimmed) {
      setErrorMsg("Person name is required.");
      return;
    }
    if (selectedGroupIds.length === 0) {
      setErrorMsg("Please select at least one group.");
      return;
    }
    setLoading(true);
    setErrorMsg(null);
    try {
      const aliases = aliasesText.split(",").map((s) => s.trim()).filter(Boolean);
      const res = await api.people.create({
        name: trimmed,
        aliases,
        gender: gender && gender !== "unknown" ? gender : undefined,
        birth_year: birthYear ? parseInt(birthYear, 10) : undefined,
        note_en: noteEn.trim() || undefined,
        group_ids: selectedGroupIds,
        primary_group_id: primaryGroupId,
      });
      onSaved(`Created person: ${res.person.name}`);
      onClose();
    } catch (err: unknown) {
      setErrorMsg((err as Error).message || "Failed to create person.");
    } finally {
      setLoading(false);
    }
  };

  const handleSaveEdit = async () => {
    if (!person) return;
    const trimmed = name.trim();
    if (!trimmed) {
      setErrorMsg("Person name is required.");
      return;
    }
    if (selectedGroupIds.length === 0) {
      setErrorMsg("Please select at least one group.");
      return;
    }
    setLoading(true);
    setErrorMsg(null);
    try {
      const aliases = aliasesText.split(",").map((s) => s.trim()).filter(Boolean);
      await api.people.update(person.id, {
        name: trimmed,
        aliases,
        gender: gender && gender !== "unknown" ? gender : undefined,
        clear_gender: gender === "unknown",
        birth_year: birthYear ? parseInt(birthYear, 10) : undefined,
        clear_birth_year: !birthYear,
        note_en: noteEn.trim() || undefined,
        clear_note_en: !noteEn.trim(),
        group_ids: selectedGroupIds,
        primary_group_id: primaryGroupId,
      });

      onSaved(`Updated person: ${trimmed}`);
      onClose();
    } catch (err: unknown) {
      setErrorMsg((err as Error).message || "Failed to update person.");
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmDelete = async () => {
    if (!person) return;
    setLoading(true);
    setErrorMsg(null);
    try {
      await api.people.remove(person.id, true);
      onSaved(`Deleted person: ${person.name}`);
      onClose();
    } catch (err: unknown) {
      setErrorMsg((err as Error).message || "Failed to delete person.");
    } finally {
      setLoading(false);
    }
  };

  const isBlockedFromDeletion = Boolean(
    deletePreview && (!deletePreview.valid || (deletePreview.warnings && deletePreview.warnings.length > 0))
  );

  return (
    <div className="modal-backdrop">
      <div className="modal-card">
        <div className="modal-header">
          <h3>
            {mode === "add" && "+ Add Person"}
            {mode === "edit" && `Edit ${person?.name}`}
            {mode === "delete" && `Delete ${person?.name}`}
          </h3>
          <button className="btn-close" onClick={onClose} aria-label="Close modal">
            &times;
          </button>
        </div>

        <div className="modal-body">
          {errorMsg && <div className="diff-card diff-invalid">{errorMsg}</div>}

          {/* ADD / EDIT FORM */}
          {mode !== "delete" && (
            <>
              {mode === "add" && duplicates.length > 0 && !allowCreateAnyway && (
                <div className="diff-card diff-warning">
                  <strong>A person with this or a similar name already exists:</strong>
                  <ul style={{ margin: "8px 0 10px", paddingLeft: 18 }}>
                    {duplicates.map((c) => (
                      <li key={c.id} style={{ marginBottom: 6 }}>
                        <span>
                          <strong>{c.name}</strong>{" "}
                          <span className="muted small">({c.reason})</span>
                        </span>
                        {onOpenExisting && (
                          <button
                            type="button"
                            className="btn btn-ghost"
                            style={{ marginLeft: 8, padding: "2px 8px", fontSize: 12 }}
                            onClick={() => {
                              onClose();
                              onOpenExisting(c.id);
                            }}
                          >
                            Open Existing Person
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
                    <span className="small muted">If this is genuinely a different person:</span>
                    <button
                      type="button"
                      className="btn btn-outline"
                      style={{ padding: "3px 10px", fontSize: 12 }}
                      onClick={() => setAllowCreateAnyway(true)}
                    >
                      Create Anyway
                    </button>
                  </div>
                </div>
              )}

              <div className="form-group">
                <label>Display Name *</label>
                <input
                  type="text"
                  className="form-input"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Mansoor Hussain"
                  autoFocus
                />
              </div>

              <div className="form-group">
                <label>Aliases / Nicknames (Comma separated)</label>
                <input
                  type="text"
                  className="form-input"
                  value={aliasesText}
                  onChange={(e) => setAliasesText(e.target.value)}
                  placeholder="Aliases: e.g. Mansoor Bhai, Uncle Mansoor, منصور بھائی"
                />
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div className="form-group">
                  <label>Gender</label>
                  <select
                    className="form-select"
                    value={gender}
                    onChange={(e) => setGender(e.target.value)}
                  >
                    <option value="unknown">Unspecified / Unknown</option>
                    <option value="male">Male</option>
                    <option value="female">Female</option>
                  </select>
                </div>
                <div className="form-group">
                  <label>Birth Year</label>
                  <input
                    type="number"
                    className="form-input"
                    value={birthYear}
                    min="1800"
                    max="2100"
                    onChange={(e) => setBirthYear(e.target.value)}
                    placeholder="e.g. 1985"
                  />
                </div>
              </div>

              {/* Group Memberships */}
              <div className="form-group">
                <label>Groups (Person can belong to multiple)</label>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 4 }}>
                  {groups.map((g) => {
                    const isChecked = selectedGroupIds.includes(g.id);
                    return (
                      <button
                        type="button"
                        key={g.id}
                        onClick={() => toggleGroup(g.id)}
                        className={`chip ${isChecked ? "chip-group" : ""}`}
                        style={{
                          cursor: "pointer",
                          padding: "6px 12px",
                          fontWeight: isChecked ? 600 : 400,
                          background: isChecked ? "var(--accent-soft)" : "#f0f2f5",
                          border: isChecked ? "1px solid var(--accent)" : "1px solid var(--line)",
                          color: isChecked ? "var(--accent-strong)" : "var(--muted)",
                        }}
                      >
                        {isChecked ? "✓ " : "+ "}
                        {g.name}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Primary Group / Folder Selector */}
              {selectedGroupIds.length > 1 && (
                <div className="form-group" style={{ marginTop: 4 }}>
                  <label>Primary Group (Canonical folder location)</label>
                  <select
                    className="form-select"
                    value={primaryGroupId}
                    onChange={(e) => setPrimaryGroupId(e.target.value)}
                  >
                    {selectedGroupIds.map((gid) => {
                      const grp = groups.find((g) => g.id === gid);
                      return (
                        <option key={gid} value={gid}>
                          {grp ? grp.name : gid}
                        </option>
                      );
                    })}
                  </select>
                  <span className="small muted">
                    The primary group determines the directory on disk (<code>Database/People/{'{group}'}/{'{id}'}/</code>).
                  </span>
                </div>
              )}

              <div className="form-group">
                <label>Personal Notes</label>
                <textarea
                  className="form-input"
                  style={{ minHeight: 64, resize: "vertical" }}
                  value={noteEn}
                  onChange={(e) => setNoteEn(e.target.value)}
                  placeholder="Optional brief notes or context..."
                />
              </div>
            </>
          )}

          {/* DELETE IMPACT REPORT */}
          {mode === "delete" && person && (
            <div className="preview-section" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div className="diff-card diff-warning">
                <strong>Safe Person Removal Preview for {person.name}:</strong>
                <p style={{ margin: "6px 0 0" }}>
                  Removing a person is a deliberate action. All direct relationship links will be disconnected, and the person's folder and journal will be safely moved to <code>Database/People/_archived/</code>.
                </p>
              </div>

              {deletePreview?.warnings && deletePreview.warnings.length > 0 && (
                <div className="diff-card diff-invalid">
                  <strong>Blocking Family Facts:</strong>
                  <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                    {deletePreview.warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                  <p className="small muted" style={{ margin: "8px 0 0" }}>
                    To preserve family integrity, core family graph connections must be removed before this person can be deleted.
                  </p>
                </div>
              )}

              {deletePreview?.direct_changes && deletePreview.direct_changes.length > 0 && (
                <div className="diff-card">
                  <strong>Direct Changes:</strong>
                  <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                    {deletePreview.direct_changes.map((change, i) => (
                      <li key={i}>{change}</li>
                    ))}
                  </ul>
                </div>
              )}

              {deletePreview?.derived_removed && deletePreview.derived_removed.length > 0 && (
                <div className="diff-card">
                  <strong>Derived Relationship Impacts ({deletePreview.derived_removed.length}):</strong>
                  <ul style={{ margin: "6px 0 0", paddingLeft: 18, maxHeight: 120, overflowY: "auto" }}>
                    {deletePreview.derived_removed.map((item, i) => (
                      <li key={i} className="small">
                        {item.person_a_name} ↔ {item.person_b_name}: {item.label_en}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button className="btn btn-outline" onClick={onClose} disabled={loading}>
            Cancel
          </button>

          {mode === "add" && (
            <button
              className="btn btn-primary"
              onClick={handleSaveAdd}
              disabled={loading || !name.trim()}
            >
              {loading ? "Creating..." : "Create Person"}
            </button>
          )}

          {mode === "edit" && (
            <button
              className="btn btn-primary"
              onClick={handleSaveEdit}
              disabled={loading || !name.trim()}
            >
              {loading ? "Saving..." : "Save Changes"}
            </button>
          )}

          {mode === "delete" && (
            <button
              className="btn btn-danger"
              onClick={handleConfirmDelete}
              disabled={loading || isBlockedFromDeletion}
              title={isBlockedFromDeletion ? "Remove family facts before deleting" : "Safely delete person"}
            >
              {loading ? "Deleting..." : isBlockedFromDeletion ? "Blocked by Family Facts" : "Confirm & Delete Person"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
