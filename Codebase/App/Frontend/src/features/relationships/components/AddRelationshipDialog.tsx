import React, { useEffect, useMemo, useState } from "react";
import { api } from "../../../api";
import type { MutationPreviewResult, Person } from "../../../types";
import { MutationPreviewDialog } from "../../mutations/components/MutationPreviewDialog";

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

  const getMutationActionAndParams = () => {
    if (!targetId) return null;

    if (domain === "family") {
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
          },
        };
      } else if (familyType === "sibling") {
        return {
          action: "add_sibling_group",
          params: {
            member_ids: [sourcePerson.id, targetId],
            type_: "full",
            ordered: false,
          },
        };
      }
    } else {
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
    const req = getMutationActionAndParams();
    if (!req) {
      setErrorMsg("Please select a target person.");
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
    const req = getMutationActionAndParams();
    if (!req || !targetPerson) {
      setErrorMsg("Please select a target person.");
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
          onSaved(`Added ${parentKind} parent-child fact between ${sourcePerson.name} and ${targetPerson.name}`);
        } else if (familyType === "marriage") {
          await api.family.addMarriage({
            person_a: sourcePerson.id,
            person_b: targetId,
            status: marriageStatus,
            year: marriageYear ? parseInt(marriageYear, 10) : undefined,
          });
          onSaved(`Added marriage between ${sourcePerson.name} and ${targetPerson.name}`);
        } else if (familyType === "sibling") {
          await api.family.addSiblingGroup([sourcePerson.id, targetId], "full", false);
          onSaved(`Added sibling fact between ${sourcePerson.name} and ${targetPerson.name}`);
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
        onSaved(`Added general relationship (${genType}) between ${sourcePerson.name} and ${targetPerson.name}`);
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
                          className="form-select"
                          value={parentRole}
                          onChange={(e) => setParentRole(e.target.value)}
                        >
                          <option value="father">Father</option>
                          <option value="mother">Mother</option>
                          <option value="parent">Parent (Unspecified gender)</option>
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
                  </>
                )}

                {familyType === "marriage" && (
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                    <div className="form-group">
                      <label>Status</label>
                      <select
                        className="form-select"
                        value={marriageStatus}
                        onChange={(e) => setMarriageStatus(e.target.value)}
                      >
                        <option value="married">Married</option>
                        <option value="divorced">Divorced</option>
                        <option value="widowed">Widowed</option>
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
                    <option value="close_friend">Close Friend</option>
                    <option value="friend">Friend</option>
                    <option value="childhood_friend">Childhood Friend</option>
                    <option value="best_friend">Best Friend</option>
                    <option value="colleague">Colleague</option>
                    <option value="former_colleague">Former Colleague</option>
                    <option value="neighbour">Neighbour</option>
                    <option value="acquaintance">Acquaintance</option>
                    <option value="mentor">Mentor / Mentee</option>
                    <option value="custom">Custom Labels</option>
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
                disabled={loading || !targetId}
                style={{ borderColor: "#0e7490", color: "#0e7490" }}
              >
                {loading ? "Calculating..." : "⚡ Preview Consequences"}
              </button>
            )}
            <button
              className="btn btn-primary"
              onClick={handleExecuteSave}
              disabled={loading || !targetId}
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
