import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { TopBar } from "../components/TopBar";
import { analyzeVideo, analyzeSampleVideo } from "../api/client";

export function UploadPage() {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [activityDescription, setActivityDescription] = useState("ASSY WITH PRESS OPERATION");
  const [stationNo, setStationNo] = useState("");
  const [activityNo, setActivityNo] = useState("");
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const mutation = useMutation({
    mutationFn: () => analyzeVideo(file!, { activityDescription, stationNo, activityNo }),
    onSuccess: (data) => navigate(`/jobs/${data.job_id}`),
  });

  const sampleMutation = useMutation({
    mutationFn: () => analyzeSampleVideo({ activityDescription, stationNo, activityNo }),
    onSuccess: (data) => navigate(`/jobs/${data.job_id}`),
  });

  function pickFile(f: File | null) {
    if (f && !f.type.startsWith("video/")) return;
    setFile(f);
  }

  const busy = mutation.isPending || sampleMutation.isPending;

  return (
    <div className="min-h-screen">
      <TopBar />

      <div className="mx-auto max-w-3xl px-6 py-16">
        <div className="mb-2 flex items-center gap-2 font-mono text-xs uppercase tracking-widest text-accent">
          <span className="inline-block h-px w-4 bg-accent" />
          Video in, MOST study out
        </div>
        <h1 className="mb-4 text-balance font-display text-[40px] font-extrabold uppercase leading-[0.98] text-ink">
          Every motion, <span className="text-accent">measured</span> automatically
        </h1>
        <p className="mb-8 max-w-[46ch] text-ink-dim">
          Upload a work cycle. Elemental motions get identified, classified, and timed
          automatically -- synced frame-for-frame with the report they build.
        </p>

        <div className="mb-8 flex items-center gap-3 rounded-md border border-line bg-raised-2 px-4 py-3">
          <div className="flex-1 text-sm text-ink-dim">
            No video handy? Run the pipeline on a real sample cycle.
          </div>
          <button
            type="button"
            disabled={busy}
            onClick={() => sampleMutation.mutate()}
            className="whitespace-nowrap rounded-md border border-line-strong bg-raised px-3.5 py-2 text-xs font-semibold text-ink hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-40"
          >
            {sampleMutation.isPending ? "Starting…" : "Try the sample cycle"}
          </button>
        </div>

        <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="sm:col-span-1">
            <label className="mb-2 block text-xs font-medium uppercase tracking-wide text-ink-faint">
              Station no.
            </label>
            <input
              type="text"
              value={stationNo}
              onChange={(e) => setStationNo(e.target.value)}
              className="w-full rounded-md border border-line-strong bg-raised px-3 py-2.5 text-sm text-ink outline-none focus:border-accent"
              placeholder="e.g. ST-04"
            />
          </div>
          <div className="sm:col-span-1">
            <label className="mb-2 block text-xs font-medium uppercase tracking-wide text-ink-faint">
              Activity no.
            </label>
            <input
              type="text"
              value={activityNo}
              onChange={(e) => setActivityNo(e.target.value)}
              className="w-full rounded-md border border-line-strong bg-raised px-3 py-2.5 text-sm text-ink outline-none focus:border-accent"
              placeholder="e.g. A-112"
            />
          </div>
          <div className="sm:col-span-1">
            <label className="mb-2 block text-xs font-medium uppercase tracking-wide text-ink-faint">
              Activity description
            </label>
            <input
              type="text"
              value={activityDescription}
              onChange={(e) => setActivityDescription(e.target.value)}
              className="w-full rounded-md border border-line-strong bg-raised px-3 py-2.5 text-sm text-ink outline-none focus:border-accent"
              placeholder="e.g. ASSY WITH PRESS OPERATION"
            />
          </div>
        </div>

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            pickFile(e.dataTransfer.files[0] ?? null);
          }}
          onClick={() => inputRef.current?.click()}
          className={`cursor-pointer rounded-md border-[1.5px] border-dashed px-6 py-10 text-center transition-colors ${
            dragging ? "border-accent bg-accent-soft" : "border-line-strong bg-raised hover:border-accent"
          }`}
        >
          <input
            ref={inputRef}
            type="file"
            accept="video/*"
            className="hidden"
            onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
          />
          <svg
            viewBox="0 0 40 40"
            fill="none"
            className="mx-auto mb-3.5 h-10 w-10"
            aria-hidden="true"
          >
            <rect x="4" y="4" width="32" height="32" rx="3" stroke="var(--color-ink-faint)" strokeWidth="1.5" />
            <path
              d="M20 26V14M20 14l-5 5M20 14l5 5"
              stroke="var(--color-accent)"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          {file ? (
            <div className="font-medium text-ink">{file.name}</div>
          ) : (
            <>
              <div className="mb-1 font-medium text-ink">Drop a work-cycle video, or click to browse</div>
              <div className="text-sm text-ink-faint">
                Faces are blurred automatically before anything leaves this screen
              </div>
            </>
          )}
        </div>

        {(mutation.isError || sampleMutation.isError) && (
          <div className="mt-4 rounded-md border border-nva bg-nva-soft px-4 py-3 text-sm text-nva">
            {((mutation.error ?? sampleMutation.error) as Error).message}
          </div>
        )}

        <div className="mt-6 flex gap-3">
          <button
            type="button"
            disabled={!file || busy}
            onClick={() => mutation.mutate()}
            className="inline-flex items-center gap-2 rounded-md bg-accent px-5 py-2.5 text-sm font-semibold text-accent-ink disabled:cursor-not-allowed disabled:opacity-40"
          >
            {mutation.isPending ? "Starting analysis…" : "Run analysis"}
          </button>
        </div>
      </div>
    </div>
  );
}
