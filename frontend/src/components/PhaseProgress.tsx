import type { JobPhase } from "../api/types";

const PHASES: { key: JobPhase; label: string }[] = [
  { key: "PREPROCESSING", label: "Blurring faces" },
  { key: "UPLOADING", label: "Uploading" },
  { key: "SEGMENTING", label: "Finding motions" },
  { key: "CLASSIFYING", label: "Classifying" },
  { key: "FINALIZING", label: "Computing TMU" },
  { key: "COMPLETED", label: "Done" },
];

export function PhaseProgress({ phase }: { phase: JobPhase }) {
  if (phase === "FAILED") {
    return (
      <div className="rounded-md border border-nva bg-nva-soft px-4 py-3 text-sm text-nva">
        Analysis failed. Check the backend logs for details.
      </div>
    );
  }

  const activeIndex = PHASES.findIndex((p) => p.key === phase);

  return (
    <div className="flex items-center gap-0">
      {PHASES.map((p, i) => {
        const done = activeIndex > i || phase === "COMPLETED";
        const active = activeIndex === i && phase !== "COMPLETED";
        return (
          <div key={p.key} className="flex flex-1 items-center">
            <div className="flex flex-col items-center gap-1.5">
              <div
                className={`h-2.5 w-2.5 rounded-full ${
                  done ? "bg-accent" : active ? "animate-pulse bg-accent" : "bg-line-strong"
                }`}
              />
              <div
                className={`whitespace-nowrap font-mono text-[10.5px] uppercase tracking-wide ${
                  done || active ? "text-ink-dim" : "text-ink-faint"
                }`}
              >
                {p.label}
              </div>
            </div>
            {i < PHASES.length - 1 && (
              <div className={`mx-1 h-px flex-1 ${done ? "bg-accent" : "bg-line-strong"}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}
