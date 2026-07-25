import type { MostRow, TaxonomyBucket } from "../api/types";

const ORDER: TaxonomyBucket[] = ["VA", "SVA", "NVA-N", "NVA", "Noise"];
const COLOR: Record<TaxonomyBucket, string> = {
  VA: "var(--color-va)",
  SVA: "var(--color-sva)",
  "NVA-N": "var(--color-nvan)",
  NVA: "var(--color-nva)",
  Noise: "var(--color-noise)",
};

export function TotalsPanel({ rows }: { rows: MostRow[] }) {
  const sums: Record<TaxonomyBucket, number> = {
    VA: 0,
    SVA: 0,
    "NVA-N": 0,
    NVA: 0,
    Noise: 0,
  };
  for (const r of rows) {
    sums.VA += r.va_sec;
    sums.SVA += r.sva_sec;
    sums["NVA-N"] += r.nvan_sec;
    sums.NVA += r.nva_sec;
  }
  const grand = ORDER.reduce((acc, k) => acc + sums[k], 0);

  return (
    <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-5">
      {ORDER.map((key) => {
        const pct = grand > 0 ? (sums[key] / grand) * 100 : 0;
        return (
          <div key={key} className="rounded-md border border-line bg-raised p-3.5">
            <div className="mb-2.5 font-mono text-[10.5px] uppercase tracking-wide text-ink-faint">{key}</div>
            <div className="mb-2 h-[5px] overflow-hidden rounded-full bg-raised-2">
              <div
                className="h-full rounded-full transition-[width] duration-500"
                style={{ width: `${pct}%`, background: COLOR[key] }}
              />
            </div>
            <div className="font-mono text-[19px] text-ink">{sums[key].toFixed(1)}s</div>
            <div className="font-mono text-[11px] text-ink-faint">{Math.round(pct)}%</div>
          </div>
        );
      })}
    </div>
  );
}
