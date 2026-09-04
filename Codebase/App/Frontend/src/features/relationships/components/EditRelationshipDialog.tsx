import React, { useEffect, useState } from "react";
import { api } from "../../../api";
import type { GeneralRelationshipFact, MutationPreviewResult, ParentChildFact, Person, RelationshipEntry } from "../../../types";
import { MutationPreviewDialog } from "../../mutations/components/MutationPreviewDialog";

interface Props {
  perspectivePerson: Person;
  targetPerson: Person;
  entry: RelationshipEntry;
  onClose: () => void;
  onSaved: (desc: string) => void;
}

export const EditRelationshipDialog: React.FC<Props> = ({
  perspectivePerson,
  targetPerson,
  entry,
  onClose,
  onSaved,
}) => {
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Stored Fact match state
  const [generalFact, setGeneralFact] = useState<GeneralRelationshipFact | null>(null);
  const [parentChildFact, setParentChildFact] = useState<ParentChildFact | null>(null);
  const [marriageFact, setMarriageFact] = useState<any | null>(null);
  const [sourcePaths, setSourcePaths] = useState<any[]>([]);

  // Form Fields
  const [genNotes, setGenNotes] = useState("");
  const [parentRole, setParentRole] = useState("parent");
  const [parentKind, setParentKind] = useState("biological");

  // Consequence Preview for Deletion
  const [previewResult, setPreviewResult] = useState<MutationPreviewResult | null>(null);
  const [pendingDeleteAction, setPendingDeleteAction] = useState<any | null>(null);

  useEffect(() => {
    loadFactsAndPaths();
  }, [perspectivePerson.id, targetPerson.id]);

  const loadFactsAndPaths = async () => {
    setLoading(true);
    try {
      if (entry.domain === "general" && !entry.derived) {
        const genRes = await api.relationships.general.list(perspectivePerson.id);
        const match = genRes.relationships.find(
          (r) =>
            (r.person_a === perspectivePerson.id && r.person_b === targetPerson.id) ||
            (r.person_b === perspectivePerson.id && r.person_a === targetPerson.id)
        );
        if (match) {
          setGeneralFact(match);
          setGenNotes(match.notes || "");
        }
      } else if (entry.domain === "family") {
        const factsRes = await api.family.facts();
        // Check direct parent-child fact
        const pcMatch = factsRes.parent_child.find(
          (pc) =>
            (pc.parent_id === perspectivePerson.id && pc.child_id === targetPerson.id) ||
            (pc.child_id === perspectivePerson.id && pc.parent_id === targetPerson.id)
        );
        if (pcMatch) {
          setParentChildFact(pcMatch);
          setParentRole(pcMatch.role);
          setParentKind(pcMatch.kind);
        }

        // Check direct marriage fact
        const mMatch = factsRes.marriages.find(
          (m) =>
            (m.spouse_a === perspectivePerson.id && m.spouse_b === targetPerson.id) ||
            (m.spouse_b === perspectivePerson.id && m.spouse_a === targetPerson.id)
        );
        if (mMatch) {
          setMarriageFact(mMatch);
        }

        // Load Show Why source paths if derived
        if (entry.derived) {
          const pathRes = await api.relationships.get(perspectivePerson.id, targetPerson.id);
          setSourcePaths(pathRes.primary || []);
        }
      }
    } catch (err: unknown) {
      setErrorMsg((err as Error).message || "Failed to load relationship detail.");
    } finally {
      setLoading(false);
    }
  };

  const handleSaveGeneral = async () => {
    if (!generalFact) return;
    setLoading(true);
    try {
      await api.relationships.general.update(generalFact.id, { notes: genNotes });
      onSaved(`Updated general relationship between ${perspectivePerson.name} and ${targetPerson.name}`);
      onClose();
    } catch (err: unknown) {
      setErrorMsg((err as Error).message || "Failed to update relationship.");
    } finally {
      setLoading(false);
    }
  };

  const handleSaveParentChild = async () => {
    if (!parentChildFact) return;
    setLoading(true);
    try {
      await api.family.updateParentChild({
        parent_id: parentChildFact.parent_id,
        child_id: parentChildFact.child_id,
        role: parentRole,
        kind: parentKind,
      });
      onSaved(`Updated parent-child fact between ${perspectivePerson.name} and ${targetPerson.name}`);
      onClose();
    } catch (err: unknown) {
      setErrorMsg((err as Error).message || "Failed to update parent-child fact.");
    } finally {
      setLoading(false);
    }
  };

  const handleDeletePreview = async (action: string, params: any) => {
    setLoading(true);
    try {
      const res = await api.mutations.preview(action, params);
      setPreviewResult(res);
      setPendingDeleteAction({ action, params });
    } catch (err: unknown) {
      setErrorMsg((err as Error).message || "Failed to preview deletion.");
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmDelete = async () => {
    if (!pendingDeleteAction) return;
    setLoading(true);
    try {
      const { action, params } = pendingDeleteAction;
      if (action === "delete_general") {
        await api.relationships.general.remove(params.relationship_id);
        onSaved(`Removed general relationship between ${perspectivePerson.name} and ${targetPerson.name}`);
      } else if (action === "delete_parent_child") {
        await api.family.deleteParentChild(params.parent_id, params.child_id);
        onSaved(`Removed parent-child fact between ${perspectivePerson.name} and ${targetPerson.name}`);
      } else if (action === "delete_marriage") {
        await api.family.deleteMarriage(params.person_a, params.person_b);
        onSaved(`Removed marriage fact between ${perspectivePerson.name} and ${targetPerson.name}`);
      }
      setPreviewResult(null);
      onClose();
    } catch (err: unknown) {
      setErrorMsg((err as Error).message || "Failed to delete relationship.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div className="modal-backdrop">
        <div className="modal-card">
          <div className="modal-header">
            <h3>
              {entry.label_en} ({perspectivePerson.name} &rarr; {targetPerson.name})
            </h3>
            <button className="btn-close" onClick={onClose}>
              &times;
            </button>
          </div>

          <div className="modal-body">
            {errorMsg && <div className="diff-card diff-invalid">{errorMsg}</div>}

            {/* Source Transparency Badge */}
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span className={`badge-fact ${entry.derived ? "badge-derived" : "badge-explicit"}`}>
                {entry.derived ? "Derived Kinship Term" : "Stored Explicit Fact"}
              </span>
              <span className="muted small">
                {entry.derived ? "Calculated by canonical engine" : "Explicitly recorded in database"}
              </span>
            </div>

            {/* DERIVED RELATIONSHIP VIEW */}
            {entry.derived && (
              <div className="path-explanation">
                <p style={{ fontWeight: 600, color: "#0e7490", marginBottom: 6 }}>
                  Why this term is derived:
                </p>
                <p>
                  <strong>{targetPerson.name}</strong> is derived as <strong>{entry.label_en}</strong> to{" "}
                  <strong>{perspectivePerson.name}</strong> based on the underlying parent-child, marriage, and sibling facts in the family graph.
                </p>

                <div style={{ marginTop: 12, padding: "8px 12px", background: "#ffffff", borderRadius: 6, border: "1px solid #d0deec" }}>
                  <strong>Source facts:</strong>
                  <ul style={{ margin: "4px 0 0", paddingLeft: 18, fontSize: 12.5 }}>
                    <li>Family graph connection: {perspectivePerson.name} &rarr; {targetPerson.name}</li>
                    {sourcePaths.map((p, idx) => (
                      <li key={idx}>{p.label_en} ({p.domain})</li>
                    ))}
                  </ul>
                </div>
                <div style={{ marginTop: 10, fontSize: 12 }} className="muted">
                  To edit this derived relationship, edit or add explicit parent-child or marriage facts.
                </div>
              </div>
            )}

            {/* EXPLICIT GENERAL FACT EDIT */}
            {generalFact && (
              <div className="form-group">
                <label>Notes</label>
                <input
                  type="text"
                  className="form-input"
                  value={genNotes}
                  onChange={(e) => setGenNotes(e.target.value)}
                  placeholder="Notes about this relationship..."
                />
              </div>
            )}

            {/* EXPLICIT PARENT-CHILD FACT EDIT */}
            {parentChildFact && (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div className="form-group">
                  <label>Role</label>
                  <select
                    className="form-select"
                    value={parentRole}
                    onChange={(e) => setParentRole(e.target.value)}
                  >
                    <option value="father">Father</option>
                    <option value="mother">Mother</option>
                    <option value="parent">Parent</option>
                  </select>
                </div>
                <div className="form-group">
                  <label>Kind</label>
                  <select
                    className="form-select"
                    value={parentKind}
                    onChange={(e) => setParentKind(e.target.value)}
                  >
                    <option value="biological">Biological</option>
                    <option value="adopted">Adopted</option>
                    <option value="step">Step</option>
                    <option value="foster">Foster</option>
                    <option value="guardian">Guardian</option>
                    <option value="unspecified">Unspecified</option>
                  </select>
                </div>
              </div>
            )}

            {/* EXPLICIT MARRIAGE FACT VIEW */}
            {marriageFact && (
              <div className="preview-direct">
                <h4>Marriage Fact</h4>
                <p>Status: {marriageFact.status} {marriageFact.year ? `(Year: ${marriageFact.year})` : ""}</p>
              </div>
            )}
          </div>

          <div className="modal-footer">
            {/* Delete button for explicit facts */}
            {!entry.derived && (
              <button
                className="btn btn-danger"
                style={{ marginRight: "auto" }}
                onClick={() => {
                  if (generalFact) {
                    handleDeletePreview("delete_general", { relationship_id: generalFact.id });
                  } else if (parentChildFact) {
                    handleDeletePreview("delete_parent_child", {
                      parent_id: parentChildFact.parent_id,
                      child_id: parentChildFact.child_id,
                    });
                  } else if (marriageFact) {
                    handleDeletePreview("delete_marriage", {
                      person_a: marriageFact.spouse_a,
                      person_b: marriageFact.spouse_b,
                    });
                  }
                }}
                disabled={loading}
              >
                Remove Fact
              </button>
            )}

            <button className="btn btn-outline" onClick={onClose} disabled={loading}>
              Close
            </button>

            {generalFact && (
              <button className="btn btn-primary" onClick={handleSaveGeneral} disabled={loading}>
                {loading ? "Saving..." : "Save Notes"}
              </button>
            )}

            {parentChildFact && (
              <button className="btn btn-primary" onClick={handleSaveParentChild} disabled={loading}>
                {loading ? "Saving..." : "Save Parent Fact"}
              </button>
            )}
          </div>
        </div>
      </div>

      {previewResult && (
        <MutationPreviewDialog
          preview={previewResult}
          onCancel={() => setPreviewResult(null)}
          onConfirm={handleConfirmDelete}
          loading={loading}
        />
      )}
    </>
  );
};
