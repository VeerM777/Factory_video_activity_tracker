import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { DataCard, ReviewFlag } from "../api/types";
import { submitReview } from "../api/client";

function FlagRow({ jobId, flag }: { jobId: string; flag: ReviewFlag }) {
  const queryClient = useQueryClient();
  const [dataCard, setDataCard] = useState<DataCard>(flag.attempted_data_card ?? "G");
  const [paramValues, setParamValues] = useState((flag.attempted_param_values ?? []).join(", "));
  const [mudaRef, setMudaRef] = useState(flag.attempted_muda_ref?.toString() ?? "");

  const mutation = useMutation({
    mutationFn: () =>
      submitReview(jobId, {
        segment_id: flag.segment_id,
        data_card: dataCard,
        param_values: paramValues
          .split(",")
          .map((v) => v.trim())
          .filter((v) => v.length > 0)
          .map(Number),
        muda_ref: Number(mudaRef),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["rows", jobId] });
      queryClient.invalidateQueries({ queryKey: ["flags", jobId] });
      queryClient.invalidateQueries({ queryKey: ["status", jobId] });
    },
  });

  const hadGuess = flag.attempted_data_card !== null;

  return (
    <div className="rounded-md border border-sva bg-sva-soft/40 p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-ink">Segment {flag.segment_id}</div>
          <div className="text-xs text-ink-dim">{flag.reason}</div>
        </div>
        {flag.confidence !== null && (
          <div className="whitespace-nowrap rounded-sm bg-sva-soft px-2 py-0.5 font-mono text-[11px] text-sva">
            {Math.round(flag.confidence * 100)}% confidence
          </div>
        )}
      </div>

      {!hadGuess && (
        <div className="mb-3 text-xs text-ink-faint">
          No model guess was returned for this segment -- fill in the correct classification below.
        </div>
      )}

      <div className="mb-3 grid grid-cols-3 gap-2.5">
        <div>
          <label className="mb-1 block text-[11px] uppercase tracking-wide text-ink-faint">Data card</label>
          <select
            value={dataCard}
            onChange={(e) => setDataCard(e.target.value as DataCard)}
            className="w-full rounded-sm border border-line-strong bg-raised px-2 py-1.5 text-sm text-ink"
          >
            <option value="G">G — General Move</option>
            <option value="C">C — Controlled Move</option>
            <option value="T">T — Tool Use</option>
            <option value="PT">PT — Process Time</option>
          </select>
        </div>
        <div>
          <label className="mb-1 block text-[11px] uppercase tracking-wide text-ink-faint">Param values</label>
          <input
            type="text"
            value={paramValues}
            onChange={(e) => setParamValues(e.target.value)}
            placeholder="1, 0, 1, 0, 0, 0, 0"
            className="w-full rounded-sm border border-line-strong bg-raised px-2 py-1.5 font-mono text-sm text-ink"
          />
        </div>
        <div>
          <label className="mb-1 block text-[11px] uppercase tracking-wide text-ink-faint">Taxonomy ref</label>
          <input
            type="number"
            value={mudaRef}
            onChange={(e) => setMudaRef(e.target.value)}
            className="w-full rounded-sm border border-line-strong bg-raised px-2 py-1.5 font-mono text-sm text-ink"
          />
        </div>
      </div>

      {mutation.isError && (
        <div className="mb-2 text-xs text-nva">{(mutation.error as Error).message}</div>
      )}

      <button
        type="button"
        disabled={mutation.isPending || !mudaRef}
        onClick={() => mutation.mutate()}
        className="rounded-sm bg-accent px-3.5 py-1.5 text-xs font-semibold text-accent-ink disabled:opacity-40"
      >
        {mutation.isPending ? "Saving…" : mutation.isSuccess ? "Saved — resubmit if needed" : "Apply correction"}
      </button>
    </div>
  );
}

export function ReviewFlagPanel({ jobId, flags }: { jobId: string; flags: ReviewFlag[] }) {
  if (flags.length === 0) return null;
  return (
    <div className="mb-6">
      <div className="mb-3 flex items-center gap-2">
        <div className="text-sm font-semibold text-ink">Needs review</div>
        <div className="rounded-full bg-sva-soft px-2 py-0.5 font-mono text-[11px] text-sva">{flags.length}</div>
      </div>
      <div className="flex flex-col gap-3">
        {flags.map((f) => (
          <FlagRow key={f.segment_id} jobId={jobId} flag={f} />
        ))}
      </div>
    </div>
  );
}
