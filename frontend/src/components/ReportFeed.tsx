import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { MostRow } from "../api/types";
import { bucketFor } from "../api/types";

const BUCKET_STYLE: Record<string, { color: string; soft: string }> = {
  VA: { color: "var(--color-va)", soft: "var(--color-va-soft)" },
  SVA: { color: "var(--color-sva)", soft: "var(--color-sva-soft)" },
  "NVA-N": { color: "var(--color-nvan)", soft: "var(--color-nvan-soft)" },
  NVA: { color: "var(--color-nva)", soft: "var(--color-nva-soft)" },
  Noise: { color: "var(--color-noise)", soft: "var(--color-noise-soft)" },
};

function fmtTime(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m < 10 ? "0" : ""}${m}:${sec < 10 ? "0" : ""}${sec}`;
}

function confidenceColor(confidence: number): string {
  if (confidence >= 0.9) return "var(--color-va)";
  if (confidence >= 0.75) return "var(--color-sva)";
  return "var(--color-nva)";
}

function ConfidenceDot({ confidence }: { confidence: number }) {
  const color = confidenceColor(confidence);
  const low = confidence < 0.75;
  return (
    <div className="flex items-center justify-end gap-1.5">
      <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: color }} />
      <span className="font-mono text-[10.5px]" style={{ color: low ? color : "var(--color-ink-faint)" }}>
        {Math.round(confidence * 100)}%{low ? " — review" : ""}
      </span>
    </div>
  );
}

interface Props {
  rows: MostRow[];
  activeIndex: number;
  onSelect: (index: number) => void;
  generating: boolean;
  autoFollow: boolean;
}

export function ReportFeed({ rows, activeIndex, onSelect, generating, autoFollow }: Props) {
  const rowRefs = useRef<(HTMLDivElement | null)[]>([]);

  useEffect(() => {
    if (!autoFollow) return;
    const el = rowRefs.current[activeIndex];
    if (el) el.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [activeIndex, autoFollow]);

  return (
    <div className="flex max-h-[620px] flex-col rounded-md border border-line bg-raised">
      <div className="flex items-center justify-between border-b border-line px-4.5 py-3.5">
        <div className="text-sm font-semibold text-ink">
          Report {generating ? "— generating" : `— ${rows.length} motions`}
        </div>
        {generating && (
          <div className="flex items-center gap-1.5 font-mono text-[10.5px] uppercase tracking-wide text-accent">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
            Live
          </div>
        )}
      </div>
      <div className="flex-1 overflow-y-auto p-1.5">
        <AnimatePresence initial={false}>
          {rows.map((row, i) => {
            const bucket = bucketFor(row);
            const style = BUCKET_STYLE[bucket];
            return (
              <motion.div
                key={row.s_no}
                ref={(el) => {
                  rowRefs.current[i] = el;
                }}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.35, delay: Math.min(i, 12) * 0.05 }}
                onClick={() => onSelect(i)}
                className={`mb-0.5 grid cursor-pointer grid-cols-[4px_1fr_auto] items-center gap-3 rounded-sm border px-3 py-2.5 hover:bg-raised-2 ${
                  i === activeIndex ? "border-accent bg-accent-soft" : "border-transparent"
                }`}
              >
                <div className="self-stretch rounded-sm" style={{ background: style.color }} />
                <div className="min-w-0">
                  <div className="truncate text-[13px] text-ink">{row.elemental_description}</div>
                  <div className="mt-0.5 flex gap-2 font-mono text-[11px] text-ink-faint">
                    <span>
                      {fmtTime(row.t_start_sec)}–{fmtTime(row.t_end_sec)}
                    </span>
                    <span>{row.activity_duration_sec.toFixed(1)}s</span>
                    <span>{row.tmu.toFixed(0)} TMU</span>
                  </div>
                </div>
                <div className="text-right">
                  <div
                    className="mb-1 whitespace-nowrap rounded-sm px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide"
                    style={{ background: style.soft, color: style.color }}
                  >
                    {bucket}
                  </div>
                  <ConfidenceDot confidence={row.confidence} />
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>
        {rows.length === 0 && (
          <div className="px-4 py-10 text-center text-sm text-ink-faint">
            {generating ? "Waiting for the first motions to be found…" : "No rows yet."}
          </div>
        )}
      </div>
    </div>
  );
}
