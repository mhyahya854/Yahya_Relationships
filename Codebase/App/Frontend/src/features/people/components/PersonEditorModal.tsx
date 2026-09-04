import React, { useEffect, useState } from "react";
import { api } from "../../../api";
import type { DuplicateCandidate, Group, MutationPreviewResult, Person } from "../../../types";

interface Props {
  mode: "add" | "edit" | "delete";
  person?: Person | null;
  groups: Group[];
  onClose: () => void;
  onSaved: (desc: string) => void;
}

export const PersonEditorModal: React.FC<Props> = ({
  mode,
  person,
  groups,
  onClose,
  onSaved,
}) => {
  const [name, setName] = useState(person?.name || "");
  const [aliasesText, setAliasesText] = useState(person?.aliases.join(", ") || "");
  const [gender, setGender] = useState<string>(person?.gender || "unknown");
  const [birthYear, setBirthYear] = useState<string>(person?.birth_year ? String(person.birth_year) : "");
  const [selectedGroupId, setSelectedGroupId] = useState<string>(
    person?.groups.find((g) => g.is_primary)?.id || groups[0]?.id || "family"
  );

  const [duplicates, setDuplicates] = useState<DuplicateCandidate[]>([]);
  const [deletePreview, setDeletePreview] = useState<MutationPreviewResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (mode === "delete" && person) {
      loadDeletePreview();
    }
  }, [mode, person?.id]);

  useEffect(() => {
    if (mode === "add" && name.trim().length >= 2) {
      const timer = setTimeout(async () => {
        try {
          const aliases = aliasesText.split(",").map((s) => s.trim()).filter(Boolean);
          const res = await api.people.checkDuplicate(name, aliases);
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

  const handleSaveAdd = async () => {
    if (!name.trim()) {
      setErrorMsg("Person name is required.");
      return;
    }
    setLoading(true);
    setErrorMsg(null);
    try {
      const aliases = aliasesText.split(",").map((s) => s.trim()).filter(Boolean);
      const res = await api.people.create({
        name: name.trim(),
        aliases,
        gender: gender || undefined,
        birth_year: birthYear ? parseInt(birthYear, 10) : undefined,
        group_id: selectedGroupId,
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
    if (!person || !name.trim()) return;
    setLoading(true);
    setErrorMsg(null);
    try {
      const aliases = aliasesText.split(",").map((s) => s.trim()).filter(Boolean);
      await api.people.update(person.id, {
        name: name.trim(),
        aliases,
        gender: gender || undefined,
        birth_year: birthYear ? parseInt(birthYear, 10) : undefined,
        clear_birth_year: !birthYear,
      });

      // Update primary group if changed
      const currentPrimary = person.groups.find((g) => g.is_primary)?.id;
      if (selectedGroupId && selectedGroupId !== currentPrimary) {
        await api.groups.assign(person.id, selectedGroupId, true);
      }

      onSaved(`Updated person: ${name.trim()}`);
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

  return (
    <div className="modal-backdrop">
      <div className="modal-card">
        <div className="modal-header">
          <h3>
            {mode === "add" && "+ Add New Person"}
            {mode === "edit" && `Edit ${person?.name}`}
            {mode === "delete" && `Delete ${person?.name}`}
          </h3>
          <button className="btn-close" onClick={onClose}>
            &times;
          </button>
        </div>

        <div className="modal-body">
          {errorMsg && <div className="diff-card diff-invalid">{errorMsg}</div>}

          {/* ADD / EDIT FORM */}
          {mode !== "delete" && (
            <>
              {duplicates.length > 0 && (
                <div className="diff-card diff-warning">
                  <strong>Possible Duplicate Person Warning:</strong>
                  <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                    {duplicates.map((c) => (
                      <li key={c.id}>
                        <strong>{c.name}</strong> ({c.reason})
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="form-group">
                <label>Full Name *</label>
                <input
                  type="text"
                  className="form-input"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Mansoor Hussain"
                />
              </div>

              <div className="form-group">
                <label>Aliases (Comma separated)</label>
                <input
                  type="text"
                  className="form-input"
                  value={aliasesText}
                  onChange={(e) => setAliasesText(e.target.value)}
                  placeholder="e.g. Mansoor Bhai, Uncle Mansoor"
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
                    <option value="male">Male</option>
                    <option value="female">Female</option>
                    <option value="unknown">Unknown</option>
                  </select>
                </div>
                <div className="form-group">
                  <label>Birth Year</label>
                  <input
                    type="number"
                    className="form-input"
                    value={birthYear}
                    onChange={(e) => setBirthYear(e.target.value)}
                    placeholder="e.g. 1985"
                  />
                </div>
              </div>

              <div className="form-group">
                <label>Organizational Group</label>
                <select
                  className="form-select"
                  value={selectedGroupId}
                  onChange={(e) => setSelectedGroupId(e.target.value)}
                >
                  {groups.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name}
                    </option>
                  ))}
                </select>
                {mode === "edit" && (
                  <span className="small muted">
                    Changing the primary group will safely relocate the person's canonical folder.
                  </span>
                )}
              </div>
            </>
          )}

          {/* DELETE IMPACT REPORT */}
          {mode === "delete" && person && (
            <div className="preview-section">
              <div className="diff-card diff-warning">
                <strong>Deletion Safety Check for {person.name}:</strong>
                <p style={{ margin: "6px 0 0" }}>
                  Deleting a person is a permanent data action. Any associated journal file will be safely archived to <code>people/_archived/</code>.
                </p>
              </div>

              {deletePreview?.warnings && deletePreview.warnings.length > 0 && (
                <div className="diff-card diff-invalid">
                  <strong>Blocking Facts &amp; Warnings:</strong>
                  <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                    {deletePreview.warnings.map((w, i) => (
                      <li key={i}>{w}</li>
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
            <button className="btn btn-primary" onClick={handleSaveAdd} disabled={loading || !name.trim()}>
              {loading ? "Creating..." : "Create Person"}
            </button>
          )}

          {mode === "edit" && (
            <button className="btn btn-primary" onClick={handleSaveEdit} disabled={loading || !name.trim()}>
              {loading ? "Saving..." : "Save Changes"}
            </button>
          )}

          {mode === "delete" && (
            <button className="btn btn-danger" onClick={handleConfirmDelete} disabled={loading}>
              {loading ? "Deleting..." : "Confirm & Delete Person"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
