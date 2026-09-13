import React, { useEffect, useMemo, useState } from "react";
import { api } from "../../../api";
import { PersonSearch } from "../../../components/ui";
import type { MutationPreviewResult, Person } from "../../../types";
import { MutationPreviewDialog } from "../../mutations/components/MutationPreviewDialog";
import {
  GENERAL_TYPES,
  MARRIAGE_CHILDREN_STATUSES,
  MARRIAGE_STATUSES,
  PARENT_KINDS,
  PARENT_ROLES,
  SIBLING_GROUP_TYPES,
} from "../constants";

interface Props {
  sourcePerson: Person;
  peopleList: Person[];
  onClose: () => void;
  onSaved: (desc: string) => void;
  initialTargetPersonId?: string;
}

export const AddRelationshipDialog: React.FC<Props> = ({
  sourcePerson,
  peopleList,
  onClose,
  onSaved,
  initialTargetPersonId,
}) => {
  const [targetSearch, setTargetSearch] = useState("");
  const [targetId, setTargetId] = useState<string>(initialTargetPersonId || "");
  const [domain, setDomain] = useState<"family" | "general">("family");

  // Family State
  const [familyType, setFamilyType] = useState<"parent_child" | "marriage" | "sibling">("parent_child");
  const [parentRole, setParentRole] = useState<string>("father");
  const [parentKind, setParentKind] = useState<string>("biological");
  const [sourceIsParent, setSourceIsParent] = useState<boolean>(true);
  const [marriageStatus, setMarriageStatus] = useState<string>("married");
  const [marriageYear, setMarriageYear] = useState<string>("");
  const [marriageChildrenStatus, setMarriageChildrenStatus] = useState<string>("");
  const [siblingType, setSiblingType] = useState<string>("");
  const [siblingOrdered, setSiblingOrdered] = useState<boolean>(false);
  const [siblingMemberIds, setSiblingMemberIds] = useState<string[]>(
    initialTargetPersonId ? [initialTargetPersonId] : []
  );

  // General State
  const [genType, setGenType] = useState<string>("close_friend");
  const [directionality, setDirectionality] = useState<"symmetric" | "directional">("symmetric");
  const [labelAToB, setLabelAToB] = useState<string>("");
  const [labelBToA, setLabelBToA] = useState<string>("");
  const [genNotes, setGenNotes] = useState<string>("");

  // Preview & Loading State
  const [previewResult, setPreviewResult] = useState<MutationPreviewResult | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const filteredTargets = useMemo(
    () =>
      peopleList.filter(
        (p) =>
          p.id !== sourcePerson.id &&
          (p.name.toLowerCase().includes(targetSearch.toLowerCase()) ||
            p.aliases.some((a) => a.toLowerCase().includes(targetSearch.toLowerCase())))
      ),
    [peopleList, sourcePerson.id, targetSearch]
  );

  const targetPerson = peopleList.find((p) => p.id === targetId);

  useEffect(() => {
    if (filteredTargets.length === 1 && targetSearch.trim()) {
      setTargetId(filteredTargets[0].id);
    }
  }, [targetSearch, filteredTargets]);

  // Keep siblingMemberIds synced if a targetId was selected before switching to sibling
  useEffect(() => {
    if (targetId && !siblingMemberIds.includes(targetId)) {
      setSiblingMemberIds((prev) => (prev.length === 0 ? [targetId] : prev));
    }
  }, [targetId]);

  const allSiblingMemberIds = useMemo(() => {
    const list = [sourcePerson.id];
    for (const id of siblingMemberIds) {
      if (!list.includes(id)) list.push(id);
    }
    return list;
  }, [sourcePerson.id, siblingMemberIds]);

  const availableSiblings = useMemo(
    () => peopleList.filter((p) => !allSiblingMemberIds.includes(p.id)),
    [peopleList, allSiblingMemberIds]
  );

  const handleAddSibling = (idToAdd: string) => {
    if (!idToAdd || allSiblingMemberIds.includes(idToAdd)) return;
    setSiblingMemberIds((prev) => [...prev, idToAdd]);
    setErrorMsg(null);
  };

  const handleRemoveSibling = (idToRemove: string) => {
    setSiblingMemberIds((prev) => prev.filter((id) => id !== idToRemove));
    setErrorMsg(null);
  };

  const isSiblingMode = domain === "family" && familyType === "sibling";
  const isFullSiblingOverLimit =
    isSiblingMode && siblingType === "full" && allSiblingMemberIds.length > 2;
  const isSiblingUnderLimit = isSiblingMode && allSiblingMemberIds.length < 2;

  const getMutationActionAndParams = () => {
    if (domain === "family") {
      if (familyType === "sibling") {
        if (allSiblingMemberIds.length < 2) return null;
        return {
          action: "add_sibling_group",
          params: {
            member_ids: allSiblingMemberIds,
            type_: siblingType || undefined,
            ordered: siblingOrdered,
          },
        };
      }
      if (!targetId) return null;
      if (familyType === "parent_child") {
        const parentId = sourceIsParent ? sourcePerson.id : targetId;
        const childId = sourceIsParent ? targetId : sourcePerson.id;
        return {
          action: "add_parent_child",
          params: {
            parent_id: parentId,
            child_id: childId,
            role: parentRole,
            kind: parentKind,
          },
        };
      } else if (familyType === "marriage") {
        return {
          action: "add_marriage",
          params: {
            person_a: sourcePerson.id,
            person_b: targetId,
            status: marriageStatus,
            year: marriageYear ? parseInt(marriageYear, 10) : null,
            children_status: marriageChildrenStatus || null,
          },
        };
      }
    } else {
      if (!targetId) return null;
      return {
        action: "add_general",
        params: {
          person_a: sourcePerson.id,
          person_b: targetId,
          type: genType,
          directionality,
          label_a_to_b: labelAToB || undefined,
          label_b_to_a: labelBToA || undefined,
          notes: genNotes || undefined,
        },
      };
    }
    return null;
  };

  const handlePreview = async () => {
    setErrorMsg(null);
    if (isFullSiblingOverLimit) {
      setErrorMsg("Full Siblings groups require exactly 2 members. Switch to Default / General Sibling Group to include 3 or more siblings.");
      return;
    }
    const req = getMutationActionAndParams();
    if (!req) {
      if (isSiblingMode) {
        setErrorMsg("Please add at least one sibling to the group.");
      } else {
        setErrorMsg("Please select a target person.");
      }
      return;
    }
    setLoading(true);
    try {
      const res = await api.mutations.preview(req.action, req.params);
      setPreviewResult(res);
    } catch (err: unknown) {
      setErrorMsg((err as Error).message || "Failed to generate preview.");
    } finally {
      setLoading(false);
    }
  };

  const handleExecuteSave = async () => {
    setErrorMsg(null);
    if (isFullSiblingOverLimit) {
      setErrorMsg("Full Siblings groups require exactly 2 members. Switch to Default / General Sibling Group to include 3 or more siblings.");
      return;
    }
    const req = getMutationActionAndParams();
    if (!req) {
      if (isSiblingMode) {
        setErrorMsg("Please add at least one sibling to the group.");
      } else {
        setErrorMsg("Please select a target person.");
      }
      return;
    }

    setLoading(true);
    try {
      if (domain === "family") {
        if (familyType === "parent_child") {
          const parentId = sourceIsParent ? sourcePerson.id : targetId;
          const childId = sourceIsParent ? targetId : sourcePerson.id;
          await api.family.addParentChild({
            parent_id: parentId,
            child_id: childId,
            role: parentRole,
            kind: parentKind,
          });
          onSaved(`Added ${parentKind} parent-child fact between ${sourcePerson.name} and ${targetPerson?.name || "child"}`);
        } else if (familyType === "marriage") {
          await api.family.addMarriage({
            person_a: sourcePerson.id,
            person_b: targetId,
            status: marriageStatus,
            year: marriageYear ? parseInt(marriageYear, 10) : undefined,
            children_status: marriageChildrenStatus || undefined,
          });
          onSaved(`Added marriage between ${sourcePerson.name} and ${targetPerson?.name || "spouse"}`);
        } else if (familyType === "sibling") {
          await api.family.addSiblingGroup(allSiblingMemberIds, siblingType || null, siblingOrdered);
          const memberNames = allSiblingMemberIds
            .map((id) => peopleList.find((p) => p.id === id)?.name || id)
            .join(", ");
          onSaved(`Added sibling group with members: ${memberNames}`);
        }
      } else {
        await api.relationships.general.add({
          person_a: sourcePerson.id,
          person_b: targetId,
          type: genType,
          directionality,
          label_a_to_b: directionality === "directional" ? labelAToB : undefined,
          label_b_to_a: directionality === "directional" ? labelBToA : undefined,
          notes: genNotes || undefined,
        });
        onSaved(`Added general relationship (${genType}) between ${sourcePerson.name} and ${targetPerson?.name || "target"}`);
      }
      onClose();
    } catch (err: unknown) {
      setErrorMsg((err as Error).message || "Failed to save relationship.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div className="modal-backdrop">
        <div className="modal-card">
          <div className="modal-header">
            <h3>+ Add Relationship from {sourcePerson.name}</h3>
            <button className="btn-close" onClick={onClose}>
              &times;
            </button>
          </div>

          <div className="modal-body">
            {errorMsg && <div className="diff-card diff-invalid">{errorMsg}</div>}

            {/* Target Person Search */}
            <div className="form-group">
              <label>Target Person *</label>
              <input
                type="text"
                id="target-person-search-input"
                className="form-input"
                placeholder="Search name or alias..."
                value={targetSearch}
                onChange={(e) => setTargetSearch(e.target.value)}
              />
              <select
                className="form-select"
                size={4}
                value={targetId}
                onChange={(e) => setTargetId(e.target.value)}
              >
                {filteredTargets.map((p) => (
                  <option
                    key={p.id}
                    value={p.id}
                    onClick={() => setTargetId(p.id)}
                  >
                    {p.name} {p.aliases.length > 0 ? `(${p.aliases.join(", ")})` : ""}
                  </option>
                ))}
              </select>
            </div>

            {/* Domain Tabs */}
            <div className="form-group">
              <label>Relationship Domain</label>
              <div style={{ display: "flex", gap: 10 }}>
                <button
                  type="button"
                  className={`btn ${domain === "family" ? "btn-primary" : "btn-outline"}`}
                  onClick={() => setDomain("family")}
                  style={{ flex: 1 }}
                >
                  Family Fact (Canonical Engine)
                </button>
                <button
                  type="button"
                  className={`btn ${domain === "general" ? "btn-primary" : "btn-outline"}`}
                  onClick={() => setDomain("general")}
                  style={{ flex: 1 }}
                >
                  General / Friend / Mentor
                </button>
              </div>
            </div>

            {/* FAMILY DOMAIN FORM */}
            {domain === "family" && (
              <>
                <div className="form-group">
                  <label>Family Fact Type</label>
                  <select
                    className="form-select"
                    value={familyType}
                    onChange={(e) => setFamilyType(e.target.value as any)}
                  >
                    <option value="parent_child">Parent / Child</option>
                    <option value="marriage">Marriage</option>
                    <option value="sibling">Sibling Fact / Group</option>
                  </select>
                </div>

                {familyType === "parent_child" && (
                  <>
                    <div className="form-group">
                      <label>Direction</label>
                      <select
                        className="form-select"
                        value={sourceIsParent ? "parent" : "child"}
                        onChange={(e) => setSourceIsParent(e.target.value === "parent")}
                      >
                        <option value="parent">
                          {sourcePerson.name} IS THE PARENT &rarr; {targetPerson?.name || "Target"} is Child
                        </option>
                        <option value="child">
                          {targetPerson?.name || "Target"} IS THE PARENT &rarr; {sourcePerson.name} is Child
                        </option>
                      </select>
                    </div>

                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                      <div className="form-group">
                        <label>Parent Role</label>
                        <select
                          id="parent-role-select"
                          data-testid="parent-role-select"
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
                          id="parent-kind-select"
                          data-testid="parent-kind-select"
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
                  </>
                )}

                {familyType === "marriage" && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                      <div className="form-group">
                        <label>Status</label>
                        <select
                          id="marriage-status-select"
                          data-testid="marriage-status-select"
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
                        id="marriage-children-status-select"
                        data-testid="marriage-children-status-select"
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

                {familyType === "sibling" && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, alignItems: "center" }}>
                      <div className="form-group">
                        <label>Sibling Group Type</label>
                        <select
                          id="add-sibling-type-select"
                          data-testid="add-sibling-type-select"
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
                          id="add-sibling-ordered-cb"
                          checked={siblingOrdered}
                          onChange={(e) => setSiblingOrdered(e.target.checked)}
                        />
                        <label htmlFor="add-sibling-ordered-cb" style={{ margin: 0, cursor: "pointer" }}>
                          Ordered (birth sequence)
                        </label>
                      </div>
                    </div>

                    {/* Sibling Members Manager */}
                    <div className="form-group" style={{ margin: 0 }}>
                      <label>Sibling Group Members * ({allSiblingMemberIds.length} members)</label>
                      <div
                        className="sibling-chips"
                        style={{
                          display: "flex",
                          flexWrap: "wrap",
                          gap: 8,
                          padding: "8px 10px",
                          background: "var(--card-bg)",
                          border: "1px solid var(--line)",
                          borderRadius: 6,
                          minHeight: 42,
                          alignItems: "center",
                        }}
                      >
                        <span className="family-badge badge-stored" style={{ padding: "4px 8px" }}>
                          {sourcePerson.name} (Source)
                        </span>
                        {siblingMemberIds.map((mId) => {
                          const person = peopleList.find((p) => p.id === mId);
                          return (
                            <span
                              key={mId}
                              id={`sibling-chip-${mId}`}
                              className="family-badge badge-explicit"
                              style={{ padding: "4px 8px", display: "inline-flex", alignItems: "center", gap: 6 }}
                            >
                              {person?.name || mId}
                              <button
                                type="button"
                                className="btn-remove-sibling"
                                onClick={() => handleRemoveSibling(mId)}
                                title="Remove from group"
                                style={{
                                  border: "none",
                                  background: "transparent",
                                  cursor: "pointer",
                                  color: "var(--danger)",
                                  fontWeight: "bold",
                                  padding: "0 2px",
                                  fontSize: 14,
                                }}
                              >
                                &times;
                              </button>
                            </span>
                          );
                        })}
                      </div>

                      {isFullSiblingOverLimit && (
                        <div className="diff-card diff-invalid" style={{ marginTop: 8, padding: "8px 12px" }}>
                          <strong>Full Siblings Group Limit:</strong> Full Siblings group requires exactly 2 members (1 source + 1 sibling). Switch to Default / General Sibling Group to include 3 or more siblings.
                        </div>
                      )}

                      {/* Add Sibling Control */}
                      <div style={{ marginTop: 10 }}>
                        <label style={{ fontSize: 12.5, fontWeight: 600, color: "var(--text-muted)" }}>
                          Add Person to Sibling Group
                        </label>
                        <div id="sibling-member-search" style={{ marginTop: 4 }}>
                          <PersonSearch
                            people={availableSiblings}
                            onSelect={(person) => handleAddSibling(person.id)}
                            placeholder="Search name or alias to add..."
                            ariaLabel="Add person to sibling group"
                            disabled={siblingType === "full" && allSiblingMemberIds.length >= 2}
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}

            {/* GENERAL DOMAIN FORM */}
            {domain === "general" && (
              <>
                <div className="form-group">
                  <label>General Type</label>
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
                    value={directionality}
                    onChange={(e) => setDirectionality(e.target.value as any)}
                  >
                    <option value="symmetric">Symmetric (A &amp; B are mutual friends/colleagues)</option>
                    <option value="directional">Directional (A &rarr; B differs from B &rarr; A)</option>
                  </select>
                </div>

                {directionality === "directional" && (
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                    <div className="form-group">
                      <label>{sourcePerson.name} &rarr; {targetPerson?.name || "B"} label</label>
                      <input
                        type="text"
                        className="form-input"
                        placeholder="e.g. Supervisor"
                        value={labelAToB}
                        onChange={(e) => setLabelAToB(e.target.value)}
                      />
                    </div>
                    <div className="form-group">
                      <label>{targetPerson?.name || "B"} &rarr; {sourcePerson.name} label</label>
                      <input
                        type="text"
                        className="form-input"
                        placeholder="e.g. Student"
                        value={labelBToA}
                        onChange={(e) => setLabelBToA(e.target.value)}
                      />
                    </div>
                  </div>
                )}

                <div className="form-group">
                  <label>Notes (Optional)</label>
                  <input
                    type="text"
                    className="form-input"
                    placeholder="e.g. Met at university in 2018"
                    value={genNotes}
                    onChange={(e) => setGenNotes(e.target.value)}
                  />
                </div>
              </>
            )}
          </div>

          <div className="modal-footer">
            <button className="btn btn-outline" onClick={onClose} disabled={loading}>
              Cancel
            </button>
            {domain === "family" && (
              <button
                className="btn btn-outline"
                onClick={handlePreview}
                disabled={loading || (isSiblingMode ? isSiblingUnderLimit || isFullSiblingOverLimit : !targetId)}
                style={{ borderColor: "var(--status-info)", color: "var(--status-info)" }}
              >
                {loading ? "Calculating..." : "⚡ Preview Consequences"}
              </button>
            )}
            <button
              className="btn btn-primary"
              onClick={handleExecuteSave}
              disabled={loading || (isSiblingMode ? isSiblingUnderLimit || isFullSiblingOverLimit : !targetId)}
            >
              {loading ? "Saving..." : "Save Fact"}
            </button>
          </div>
        </div>
      </div>

      {previewResult && (
        <MutationPreviewDialog
          preview={previewResult}
          onCancel={() => setPreviewResult(null)}
          onConfirm={() => {
            setPreviewResult(null);
            handleExecuteSave();
          }}
          loading={loading}
        />
      )}
    </>
  );
};
