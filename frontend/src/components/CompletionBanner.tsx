import { motion } from "framer-motion";

function fmtDuration(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  if (m === 0) return `${s}s`;
  return `${m}m ${s}s`;
}

interface Props {
  elapsedSec: number;
  estimatedManualSec: number;
  rowCount: number;
}

export function CompletionBanner({ elapsedSec, estimatedManualSec, rowCount }: Props) {
  const speedup = estimatedManualSec > 0 ? Math.round(estimatedManualSec / Math.max(elapsedSec, 1)) : 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: -8, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="mb-6 flex flex-wrap items-center gap-x-8 gap-y-3 rounded-md border border-va bg-va-soft px-5 py-4"
    >
      <div className="flex items-center gap-2.5">
        <svg viewBox="0 0 20 20" className="h-5 w-5 shrink-0" fill="none" aria-hidden="true">
          <circle cx="10" cy="10" r="9" stroke="var(--color-va)" strokeWidth="1.5" />
          <path d="M6 10.5l2.5 2.5 5.5-6" stroke="var(--color-va)" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <div className="font-display text-lg font-extrabold uppercase text-va">Analysis complete</div>
      </div>

      <div className="flex items-baseline gap-1.5">
        <span className="font-mono text-2xl text-ink">{fmtDuration(elapsedSec)}</span>
        <span className="text-xs text-ink-faint">automated · {rowCount} motions</span>
      </div>

      <div className="flex items-baseline gap-1.5">
        <span className="font-mono text-lg text-ink-dim line-through decoration-ink-faint">
          ~{fmtDuration(estimatedManualSec)}
        </span>
        <span className="text-xs text-ink-faint">estimated manual study</span>
      </div>

      {speedup > 1 && (
        <div className="rounded-sm border border-va bg-raised px-2.5 py-1 font-mono text-xs font-semibold text-va">
          ~{speedup}x faster
        </div>
      )}
    </motion.div>
  );
}
