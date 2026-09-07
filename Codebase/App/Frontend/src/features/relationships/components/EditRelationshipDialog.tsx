import React, { useEffect, useState } from "react";
import { api } from "../../../api";
import type {
  GeneralRelationshipFact,
  MarriageFact,
  MutationPreviewResult,
  ParentChildFact,
  Person,
  RelationshipEntry,
  SiblingGroupFact,
} from "../../../types";
import { MutationPreviewDialog } from "../../mutations/components/MutationPreviewDialog";
import { relationshipsApi } from "../api";
import {
  GENERAL_TYPES,
  MARRIAGE_CHILDREN_STATUSES,
  MARRIAGE_STATUSES,
  PARENT_KINDS,
  PARENT_ROLES,
  SIBLING_GROUP_TYPES,
} from "../constants";

interface Props {
  perspectivePerson: Person;
  targetPerson: Person;
  entry: RelationshipEntry;
  onClose: () => void;
  onSaved: (desc: string) => void;
  initialDeleteMode?: boolean;
}

export interface PerspectiveDirectionalLabels {
  perspectiveToTarget: string;
  targetToPerspective: string;
}

export function toPerspectiveLabels(
  fact: {
    directionality: string;
    direction_from?: string | null;
    label_a_to_b?: string | null;
    label_b_to_a?: string | null;
  },
  perspectivePersonId: string,
): PerspectiveDirectionalLabels {
  const isDirectional = fact.directionality === "directional";
  if (!isDirectional) {
    const mutual = fact.label_a_to_b || fact.label_b_to_a || "";
    return {
      perspectiveToTarget: mutual,
      targetToPerspective: mutual,
    };
  }
  if (fact.direction_from === perspectivePersonId) {
    return {
      perspectiveToTarget: fact.label_a_to_b || "",
      targetToPerspective: fact.label_b_to_a || "",
    };
  }
  return {
    perspectiveToTarget: fact.label_b_to_a || "",
    targetToPerspective: fact.label_a_to_b || "",
  };
}

export function toStoredDirectionalLabels(params: {
  perspectiveToTarget: string;
  targetToPerspective: string;
  directionFrom: string;
  perspectivePersonId: string;
  directionality: "symmetric" | "directional";
  relType: string;
}): { label_a_to_b: string | null; label_b_to_a: string | null } {
  const {
    perspectiveToTarget,
    targetToPerspective,
    directionFrom,
    perspectivePersonId,
    directionality,
    relType,
  } = params;

  if (directionality === "symmetric") {
    if (relType === "custom") {
      const mutual = perspectiveToTarget.trim() || targetToPerspective.trim() || null;
      return { label_a_to_b: mutual, label_b_to_a: mutual };
    }
    return { label_a_to_b: null, label_b_to_a: null };
  }

  const pToT = perspectiveToTarget.trim() || null;
  const tToP = targetToPerspective.trim() || null;
  if (directionFrom === perspectivePersonId) {
    return {
      label_a_to_b: pToT,
      label_b_to_a: tToP,
    };
  } else {
    return {
      label_a_to_b: tToP,
      label_b_to_a: pToT,
    };
  }
}

export const EditRelationshipDialog: React.FC<Props> = ({
  perspectivePerson,
  targetPerson,
  entry,
  onClose,
  onSaved,
  initialDeleteMode = false,
}) => {
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Stored Fact match state
  const [generalFact, setGeneralFact] = useState<GeneralRelationshipFact | null>(null);
  const [parentChildFact, setParentChildFact] = useState<ParentChildFact | null>(null);
  const [marriageFact, setMarriageFact] = useState<MarriageFact | null>(null);
  const [siblingGroupFact, setSiblingGroupFact] = useState<SiblingGroupFact | null>(null);
  const [sourcePaths, setSourcePaths] = useState<any[]>([]);
  const [peopleMap, setPeopleMap] = useState<Record<string, string>>({});

  // General Form Fields
  const [genType, setGenType] = useState("close_friend");
  const [genDirectionality, setGenDirectionality] = useState<"symmetric" | "directional">("symmetric");
  const [genDirectionFrom, setGenDirectionFrom] = useState<string>(perspectivePerson.id);
  const [perspectiveToTargetLabel, setPerspectiveToTargetLabel] = useState("");
  const [targetToPerspectiveLabel, setTargetToPerspectiveLabel] = useState("");
  const [genNotes, setGenNotes] = useState("");

  // Parent-Child Form Fields
  const [parentRole, setParentRole] = useState("parent");
  const [parentKind, setParentKind] = useState("biological");

  // Marriage Form Fields
  const [marriageStatus, setMarriageStatus] = useState("married");
  const [marriageYear, setMarriageYear] = useState("");
  const [marriageChildrenStatus, setMarriageChildrenStatus] = useState("");

  // Sibling Group Form Fields
  const [siblingType, setSiblingType] = useState("");
  const [siblingOrdered, setSiblingOrdered] = useState(false);

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
        const match = genRes.relationships.find((r) => {
          if (entry.general_relationship_id) {
            return r.id === entry.general_relationship_id;
          }
          return (
            (r.person_a === perspectivePerson.id && r.person_b === targetPerson.id) ||
            (r.person_b === perspectivePerson.id && r.person_a === targetPerson.id)
          );
        });
        if (match) {
          setGeneralFact(match);
          setGenType(match.type);
          setGenDirectionality(match.directionality);
          setGenDirectionFrom(match.direction_from || match.person_a);
          const labels = toPerspectiveLabels(match, perspectivePerson.id);
          setPerspectiveToTargetLabel(labels.perspectiveToTarget);
          setTargetToPerspectiveLabel(labels.targetToPerspective);
          setGenNotes(match.notes || "");
        }
      } else if (entry.domain === "family") {
        const factsRes = await api.family.facts();
        const pMap: Record<string, string> = {};
        factsRes.people?.forEach((p) => {
          pMap[p.id] = p.name;
        });
        setPeopleMap(pMap);

        if (!entry.derived) {
          const kind = entry.stored_fact_kind;

          // Check direct parent-child fact
          if (!kind || kind === "parent_child") {
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
          }

          // Check direct marriage fact
          if (!kind || kind === "marriage") {
            const mMatch = factsRes.marriages.find(
              (m) =>
                (m.spouse_a === perspectivePerson.id && m.spouse_b === targetPerson.id) ||
                (m.spouse_b === perspectivePerson.id && m.spouse_a === targetPerson.id)
            );
            if (mMatch) {
              setMarriageFact(mMatch);
              setMarriageStatus(mMatch.status || "married");
              setMarriageYear(mMatch.year ? String(mMatch.year) : "");
              setMarriageChildrenStatus(mMatch.children_status || "");
            }
          }

          // Check direct sibling group fact
          if (!kind || kind === "sibling_group") {
            const sgMatch = factsRes.sibling_groups?.find(
              (g) =>
                g.members?.includes(perspectivePerson.id) &&
                g.members?.includes(targetPerson.id)
            );
            if (sgMatch) {
              setSiblingGroupFact(sgMatch);
              setSiblingType(sgMatch.type || "");
              setSiblingOrdered(Boolean(sgMatch.ordered));
            }
          }
        } else {
          // Load Show Why source paths if derived
          const pathRes = await relationshipsApi.paths(perspectivePerson.id, targetPerson.id);
          const pIds = entry.path_ids || [];
          const matched = pathRes.paths.filter(
            (p) =>
              pIds.includes(p.id) ||
              (p.semantic_id || p.relationship_type) === (entry.semantic_id || entry.relationship_type)
          );
          setSourcePaths(matched.length ? matched : pathRes.paths);
        }
      }
    } catch (err: unknown) {
      setErrorMsg((err as Error).message || "Failed to load relationship detail.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (initialDeleteMode && !entry.derived && !previewResult && !pendingDeleteAction) {
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
      } else if (siblingGroupFact) {
        handleDeletePreview("delete_sibling_group", {
          group_id: siblingGroupFact.id,
        });
      }
    }
  }, [initialDeleteMode, entry.derived, generalFact, parentChildFact, marriageFact, siblingGroupFact, previewResult, pendingDeleteAction]);

  const handleSaveGeneral = async () => {
    if (!generalFact) return;
    setLoading(true);
    setErrorMsg(null);
    try {
      if (genDirectionality === "directional") {
        if (!perspectiveToTargetLabel.trim() || !targetToPerspectiveLabel.trim()) {
          throw new Error("Directional relationships require both labels.");
        }
      } else if (genType === "custom") {
        if (!perspectiveToTargetLabel.trim()) {
          throw new Error("Custom symmetric relationships require a mutual label.");
        }
      }

      const storedLabels = toStoredDirectionalLabels({
        perspectiveToTarget: perspectiveToTargetLabel,
        targetToPerspective: targetToPerspectiveLabel,
        directionFrom: genDirectionFrom,
        perspectivePersonId: perspectivePerson.id,
        directionality: genDirectionality,
        relType: genType,
      });

      await api.relationships.general.update(generalFact.id, {
        type: genType,
        directionality: genDirectionality,
        direction_from: genDirectionality === "directional" ? genDirectionFrom : null,
        label_a_to_b: storedLabels.label_a_to_b,
        label_b_to_a: storedLabels.label_b_to_a,
        notes: genNotes.trim() ? genNotes.trim() : null,
      });
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
    setErrorMsg(null);
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

  const handleSaveMarriage = async () => {
    if (!marriageFact) return;
    setLoading(true);
    setErrorMsg(null);
    try {
      await api.family.updateMarriage({
        person_a: marriageFact.spouse_a,
        person_b: marriageFact.spouse_b,
        status: marriageStatus,
        year: marriageYear ? parseInt(marriageYear, 10) : null,
        children_status: marriageChildrenStatus || null,
      });
      onSaved(`Updated marriage fact between ${perspectivePerson.name} and ${targetPerson.name}`);
      onClose();
    } catch (err: unknown) {
      setErrorMsg((err as Error).message || "Failed to update marriage fact.");
    } finally {
      setLoading(false);
    }
  };

  const handleSaveSiblingGroup = async () => {
    if (!siblingGroupFact) return;
    setLoading(true);
    setErrorMsg(null);
    try {
      await api.family.updateSiblingGroup(siblingGroupFact.id, {
        type: siblingType || null,
        ordered: siblingOrdered,
      });
      onSaved(`Updated sibling group fact between ${perspectivePerson.name} and ${targetPerson.name}`);
      onClose();
    } catch (err: unknown) {
      setErrorMsg((err as Error).message || "Failed to update sibling group fact.");
    } finally {
      setLoading(false);
    }
  };

  const handleDeletePreview = async (action: string, params: any) => {
    setLoading(true);
    setErrorMsg(null);
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
    setErrorMsg(null);
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
      } else if (action === "delete_sibling_group") {
        await api.family.deleteSiblingGroup(params.group_id);
        onSaved(`Removed sibling group fact between ${perspectivePerson.name} and ${targetPerson.name}`);
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
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
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
                  <strong>Underlying lineage & stored fact path{sourcePaths.length > 1 ? "s" : ""}:</strong>
                  <ul style={{ margin: "4px 0 0", paddingLeft: 18, fontSize: 12.5 }}>
                    {sourcePaths.map((p, idx) => (
                      <li key={idx} style={{ marginBottom: 4 }}>
                        <strong>{p.label_en}</strong>: {p.nodes.map((n: any) => n.name).join(" → ")}
                        {p.explanation && <div className="muted tiny" style={{ marginTop: 1 }}>{p.explanation}</div>}
                      </li>
                    ))}
                  </ul>
                </div>
                <div style={{ marginTop: 10, fontSize: 12 }} className="muted">
                  To change this derived relationship, edit or remove the underlying stored parent-child or marriage facts shown above.
                </div>
              </div>
            )}

            {/* EXPLICIT GENERAL FACT EDIT */}
            {generalFact && (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <div className="form-group">
                  <label>Relationship Type</label>
                  <select
                    className="form-select"
                    value={genType}
                    onChange={(e) => setGenType(e.target.value)}
                  >
                    {GENERAL_TYPES.map((t) => (
                      <option key={t.value} value={t.value}>
                        {t.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="form-group">
                  <label>Directionality</label>
                  <select
                    className="form-select"
                    value={genDirectionality}
                    onChange={(e) => setGenDirectionality(e.target.value as "symmetric" | "directional")}
                  >
                    <option value="symmetric">Symmetric (Mutual relation)</option>
                    <option value="directional">Directional (Different roles/labels)</option>
                  </select>
                </div>

                {genDirectionality === "directional" && (
                  <div className="form-group">
                    <label>Direction From</label>
                    <select
                      className="form-select"
                      value={genDirectionFrom}
                      onChange={(e) => setGenDirectionFrom(e.target.value)}
                    >
                      <option value={perspectivePerson.id}>From {perspectivePerson.name}</option>
                      <option value={targetPerson.id}>From {targetPerson.name}</option>
                    </select>
                  </div>
                )}

                {genDirectionality === "directional" && (
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                    <div className="form-group">
                      <label>{perspectivePerson.name} &rarr; {targetPerson.name} label</label>
                      <input
                        type="text"
                        className="form-input"
                        placeholder="e.g. Mentor"
                        value={perspectiveToTargetLabel}
                        onChange={(e) => setPerspectiveToTargetLabel(e.target.value)}
                      />
                    </div>
                    <div className="form-group">
                      <label>{targetPerson.name} &rarr; {perspectivePerson.name} label</label>
                      <input
                        type="text"
                        className="form-input"
                        placeholder="e.g. Mentee"
                        value={targetToPerspectiveLabel}
                        onChange={(e) => setTargetToPerspectiveLabel(e.target.value)}
                      />
                    </div>
                  </div>
                )}

                {genDirectionality === "symmetric" && genType === "custom" && (
                  <div className="form-group">
                    <label>Mutual Relationship Label</label>
                    <input
                      type="text"
                      className="form-input"
                      placeholder="e.g. Co-founders"
                      value={perspectiveToTargetLabel}
                      onChange={(e) => {
                        setPerspectiveToTargetLabel(e.target.value);
                        setTargetToPerspectiveLabel(e.target.value);
                      }}
                    />
                  </div>
                )}

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
                    {PARENT_ROLES.map((r) => (
                      <option key={r.value} value={r.value}>
                        {r.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label>Kind</label>
                  <select
                    className="form-select"
                    value={parentKind}
                    onChange={(e) => setParentKind(e.target.value)}
                  >
                    {PARENT_KINDS.map((k) => (
                      <option key={k.value} value={k.value}>
                        {k.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            )}

            {/* EXPLICIT MARRIAGE FACT EDIT */}
            {marriageFact && (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                  <div className="form-group">
                    <label>Status</label>
                    <select
                      className="form-select"
                      value={marriageStatus}
                      onChange={(e) => setMarriageStatus(e.target.value)}
                    >
                      {MARRIAGE_STATUSES.map((s) => (
                        <option key={s.value} value={s.value}>
                          {s.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Marriage Year (Optional)</label>
                    <input
                      type="number"
                      className="form-input"
                      placeholder="e.g. 1998"
                      value={marriageYear}
                      onChange={(e) => setMarriageYear(e.target.value)}
                    />
                  </div>
                </div>
                <div className="form-group">
                  <label>Children Status</label>
                  <select
                    className="form-select"
                    value={marriageChildrenStatus}
                    onChange={(e) => setMarriageChildrenStatus(e.target.value)}
                  >
                    {MARRIAGE_CHILDREN_STATUSES.map((cs) => (
                      <option key={cs.value} value={cs.value}>
                        {cs.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            )}

            {/* EXPLICIT SIBLING GROUP FACT EDIT */}
            {siblingGroupFact && (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <div className="preview-direct" style={{ margin: 0 }}>
                  <p style={{ margin: 0, fontWeight: 600 }}>
                    Group ID: {siblingGroupFact.id}
                  </p>
                  <div className="muted small" style={{ marginTop: 4 }}>
                    Members: {siblingGroupFact.members.map((m) => peopleMap[m] || m).join(", ")}
                  </div>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, alignItems: "center" }}>
                  <div className="form-group">
                    <label>Sibling Group Type</label>
                    <select
                      className="form-select"
                      value={siblingType}
                      onChange={(e) => setSiblingType(e.target.value)}
                    >
                      {SIBLING_GROUP_TYPES.map((st) => (
                        <option key={st.value} value={st.value}>
                          {st.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="form-group" style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 22 }}>
                    <input
                      type="checkbox"
                      id="sibling-ordered-cb"
                      checked={siblingOrdered}
                      onChange={(e) => setSiblingOrdered(e.target.checked)}
                    />
                    <label htmlFor="sibling-ordered-cb" style={{ margin: 0, cursor: "pointer" }}>
                      Ordered (birth-order sequence)
                    </label>
                  </div>
                </div>

                <div className="muted tiny" style={{ marginTop: 2 }}>
                  Note: Group membership is immutable. To add or remove siblings from this group, remove this fact and record a new sibling group.
                </div>
              </div>
            )}
          </div>

          <div className="modal-footer">
            {/* Delete button for explicit facts */}
            {!entry.derived && (generalFact || parentChildFact || marriageFact || siblingGroupFact) && (
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
                  } else if (siblingGroupFact) {
                    handleDeletePreview("delete_sibling_group", {
                      group_id: siblingGroupFact.id,
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

            {!entry.derived && generalFact && (
              <button className="btn btn-primary" onClick={handleSaveGeneral} disabled={loading}>
                {loading ? "Saving..." : "Save Relationship Fact"}
              </button>
            )}

            {!entry.derived && parentChildFact && (
              <button className="btn btn-primary" onClick={handleSaveParentChild} disabled={loading}>
                {loading ? "Saving..." : "Save Parent Fact"}
              </button>
            )}

            {!entry.derived && marriageFact && (
              <button className="btn btn-primary" onClick={handleSaveMarriage} disabled={loading}>
                {loading ? "Saving..." : "Save Marriage Fact"}
              </button>
            )}

            {!entry.derived && siblingGroupFact && (
              <button className="btn btn-primary" onClick={handleSaveSiblingGroup} disabled={loading}>
                {loading ? "Saving..." : "Save Sibling Group Fact"}
              </button>
            )}
          </div>
        </div>
      </div>

      {previewResult && (
        <MutationPreviewDialog
          preview={previewResult}
          onCancel={() => {
            setPreviewResult(null);
            setPendingDeleteAction(null);
            if (initialDeleteMode) {
              onClose();
            }
          }}
          onConfirm={handleConfirmDelete}
          loading={loading}
        />
      )}
    </>
  );
};
