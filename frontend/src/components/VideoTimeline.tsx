import { type RefObject } from "react";
import type { MostRow } from "../api/types";
import { bucketFor } from "../api/types";

const BUCKET_COLOR: Record<string, string> = {
  VA: "var(--color-va)",
  SVA: "var(--color-sva)",
  "NVA-N": "var(--color-nvan)",
  NVA: "var(--color-nva)",
  Noise: "var(--color-noise)",
};

function fmtTime(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m < 10 ? "0" : ""}${m}:${sec < 10 ? "0" : ""}${sec}`;
}

interface Props {
  videoSrc: string;
  videoRef: RefObject<HTMLVideoElement | null>;
  rows: MostRow[];
  activeIndex: number;
  currentTime: number;
  duration: number;
  onSeek: (time: number) => void;
}

export function VideoTimeline({ videoSrc, videoRef, rows, activeIndex, currentTime, duration, onSeek }: Props) {
  const total = duration > 0 ? duration : rows.length ? rows[rows.length - 1].t_end_sec : 1;

  return (
    <div className="overflow-hidden rounded-md border border-line bg-raised">
      <div className="relative aspect-video border-b border-line bg-raised-2">
        <video
          ref={videoRef}
          src={videoSrc}
          controls
          className="h-full w-full object-contain"
          preload="metadata"
        />
      </div>

      <div className="px-4 py-3.5">
        <div
          className="relative h-[34px] cursor-pointer overflow-hidden rounded-sm border border-line bg-raised-2"
          onClick={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const pct = (e.clientX - rect.left) / rect.width;
            onSeek(pct * total);
          }}
        >
          {rows.map((row, i) => {
            const bucket = bucketFor(row);
            const left = (row.t_start_sec / total) * 100;
            const width = ((row.t_end_sec - row.t_start_sec) / total) * 100;
            return (
              <div
                key={row.s_no}
                title={row.elemental_description}
                className={`absolute top-0 bottom-0 border-r border-ground transition-opacity ${
                  i === activeIndex ? "opacity-100" : "opacity-55 hover:opacity-90"
                }`}
                style={{ left: `${left}%`, width: `${width}%`, background: BUCKET_COLOR[bucket] }}
              />
            );
          })}
          {total > 0 && (
            <div
              className="pointer-events-none absolute -top-[3px] -bottom-[3px] z-10 w-0.5 bg-ink transition-[left] duration-150"
              style={{ left: `${(currentTime / total) * 100}%` }}
            >
              <div className="absolute -top-1 left-1/2 h-2 w-2 -translate-x-1/2 rounded-full bg-ink" />
            </div>
          )}
        </div>
        <div className="mt-1.5 flex justify-between font-mono text-[10.5px] text-ink-faint">
          <span>{fmtTime(0)}</span>
          <span>
            {fmtTime(currentTime)} / {fmtTime(total)}
          </span>
        </div>
      </div>
    </div>
  );
}
