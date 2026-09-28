export type RestoreStage = "verifying" | "restoring" | "complete";

const LABELS: Record<RestoreStage, string> = {
  verifying: "Verifying backup manifest, payload, and schema…",
  restoring: "Creating the safety backup and restoring under the maintenance lock…",
  complete: "Restore completed and post-restore health checks passed.",
};

export function RestoreProgress({ currentStage }: { currentStage: RestoreStage }) {
  return (
    <div className="info-note" role="status" aria-live="polite">
      <strong>{currentStage === "complete" ? "Complete ✓" : "Working"}</strong>
      <div className="small" style={{ marginTop: 4 }}>{LABELS[currentStage]}</div>
    </div>
  );
}
