export type RestoreStage =
  | "verifying"
  | "safety_backup"
  | "staging"
  | "validating"
  | "switching"
  | "complete";

const STAGES: Array<{ id: RestoreStage; label: string }> = [
  { id: "verifying", label: "Verifying backup manifest & hashes" },
  { id: "safety_backup", label: "Creating safety backup of current state" },
  { id: "staging", label: "Staging restore into temporary root" },
  { id: "validating", label: "Validating database & filesystem integrity" },
  { id: "switching", label: "Switching active data root" },
  { id: "complete", label: "Restore completed successfully" },
];

export function RestoreProgress({ currentStage }: { currentStage: RestoreStage }) {
  const currentIndex = STAGES.findIndex((s) => s.id === currentStage);

  return (
    <div style={{ padding: "12px 0", display: "flex", flexDirection: "column", gap: "10px" }}>
      <div
        style={{
          height: "6px",
          width: "100%",
          background: "#e2e8f0",
          borderRadius: "999px",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${Math.min(100, Math.max(10, ((currentIndex + 1) / STAGES.length) * 100))}%`,
            background: "var(--accent-strong, #2563eb)",
            transition: "width 0.3s ease",
          }}
        />
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
        {STAGES.map((stage, idx) => {
          const isDone = idx < currentIndex;
          const isCurrent = idx === currentIndex;
          return (
            <div
              key={stage.id}
              style={{
                fontSize: "12.5px",
                display: "flex",
                alignItems: "center",
                gap: "8px",
                color: isCurrent ? "var(--accent-strong, #2563eb)" : isDone ? "var(--ok, #16a34a)" : "#94a3b8",
                fontWeight: isCurrent ? 600 : 400,
              }}
            >
              <span>{isDone ? "✓" : isCurrent ? "●" : "○"}</span>
              <span>{stage.label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
