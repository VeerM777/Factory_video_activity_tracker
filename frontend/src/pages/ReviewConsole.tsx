import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { TopBar } from "../components/TopBar";
import { PhaseProgress } from "../components/PhaseProgress";
import { VideoTimeline } from "../components/VideoTimeline";
import { ReportFeed } from "../components/ReportFeed";
import { TotalsPanel } from "../components/TotalsPanel";
import { ReviewFlagPanel } from "../components/ReviewFlagPanel";
import { CompletionBanner } from "../components/CompletionBanner";
import { getJobStatus, getJobRows, getJobFlags, excelDownloadUrl, videoUrl } from "../api/client";

const TERMINAL = new Set(["COMPLETED", "FAILED"]);

export function ReviewConsole() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const videoRef = useRef<HTMLVideoElement>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);

  const statusQuery = useQuery({
    queryKey: ["status", jobId],
    queryFn: () => getJobStatus(jobId!),
    enabled: !!jobId,
    refetchInterval: (query) => {
      if (query.state.status === "error" || (query.state.data && TERMINAL.has(query.state.data.status))) {
        return false;
      }
      return 2000;
    },
    refetchIntervalInBackground: true,
  });

  const isDone = statusQuery.data?.status === "COMPLETED";
  const isFailed = statusQuery.data?.status === "FAILED";

  const rowsQuery = useQuery({
    queryKey: ["rows", jobId],
    queryFn: () => getJobRows(jobId!),
    enabled: !!jobId && !isFailed,
    refetchInterval: isDone || isFailed ? false : 2000,
    refetchIntervalInBackground: true,
  });

  const flagsQuery = useQuery({
    queryKey: ["flags", jobId],
    queryFn: () => getJobFlags(jobId!),
    enabled: !!jobId && isDone,
  });

  const rows = useMemo(() => rowsQuery.data ?? [], [rowsQuery.data]);

  useEffect(() => {
    const el = videoRef.current;
    if (!el) return;
    const onTime = () => setCurrentTime(el.currentTime);
    const onMeta = () => setDuration(el.duration || 0);
    const onPlay = () => setIsPlaying(true);
    const onPause = () => setIsPlaying(false);
    el.addEventListener("timeupdate", onTime);
    el.addEventListener("loadedmetadata", onMeta);
    el.addEventListener("play", onPlay);
    el.addEventListener("pause", onPause);
    el.addEventListener("ended", onPause);
    return () => {
      el.removeEventListener("timeupdate", onTime);
      el.removeEventListener("loadedmetadata", onMeta);
      el.removeEventListener("play", onPlay);
      el.removeEventListener("pause", onPause);
      el.removeEventListener("ended", onPause);
    };
  }, [jobId]);

  const activeIndex = useMemo(() => {
    return rows.findIndex((r) => currentTime >= r.t_start_sec && currentTime < r.t_end_sec);
  }, [rows, currentTime]);

  function seek(time: number) {
    if (videoRef.current) videoRef.current.currentTime = time;
  }

  if (!jobId) return null;

  const phase = statusQuery.data?.phase ?? "QUEUED";
  const generating = !isDone && !isFailed;
  const stationNo = rows[0]?.station_no;
  const activityNo = rows[0]?.activity_no;

  return (
    <div className="min-h-screen">
      <TopBar />
      <div className="mx-auto max-w-6xl px-6 py-8">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="font-display text-2xl font-extrabold uppercase text-ink">Review</div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-xs text-ink-faint">
              <span>job {jobId}</span>
              {stationNo && <span>· station {stationNo}</span>}
              {activityNo && <span>· activity {activityNo}</span>}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => navigate("/")}
              className="rounded-md border border-line-strong bg-raised px-3.5 py-2 text-xs font-semibold text-ink hover:border-accent hover:text-accent"
            >
              ← Back to Upload
            </button>
            {isDone && (
              <a
                href={excelDownloadUrl(jobId)}
                className="inline-flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-ink no-underline"
              >
                Download workbook (.xlsx)
              </a>
            )}
          </div>
        </div>

        {statusQuery.isError && (
          <div className="mb-8 rounded-md border border-nva bg-nva-soft p-5 text-nva">
            <div className="font-semibold text-base mb-1">Job Not Found or Connection Lost</div>
            <div className="text-sm opacity-90 mb-4">
              {(statusQuery.error as Error)?.message || "Unable to retrieve job status from backend server."}
            </div>
            <button
              type="button"
              onClick={() => navigate("/")}
              className="rounded bg-nva px-4 py-2 text-xs font-bold text-white hover:opacity-90"
            >
              Start New Analysis
            </button>
          </div>
        )}

        {isFailed && (
          <div className="mb-8 rounded-md border border-nva bg-nva-soft p-5 text-nva">
            <div className="font-semibold text-base mb-1">Analysis Failed</div>
            <div className="text-sm opacity-90 mb-4">
              {statusQuery.data?.error || "An error occurred during video analysis execution."}
            </div>
            <button
              type="button"
              onClick={() => navigate("/")}
              className="rounded bg-nva px-4 py-2 text-xs font-bold text-white hover:opacity-90"
            >
              Try Again
            </button>
          </div>
        )}

        {!isDone && !isFailed && !statusQuery.isError && (
          <div className="mb-8 rounded-md border border-line bg-raised p-5">
            <PhaseProgress phase={phase} />
          </div>
        )}

        {isDone && statusQuery.data?.elapsed_sec != null && statusQuery.data?.estimated_manual_sec != null && (
          <CompletionBanner
            elapsedSec={statusQuery.data.elapsed_sec}
            estimatedManualSec={statusQuery.data.estimated_manual_sec}
            rowCount={rows.length}
          />
        )}

        <div className="mb-6 grid grid-cols-1 gap-5 lg:grid-cols-2">
          <VideoTimeline
            videoSrc={videoUrl(jobId)}
            videoRef={videoRef}
            rows={rows}
            activeIndex={activeIndex}
            currentTime={currentTime}
            duration={duration}
            onSeek={seek}
          />
          <ReportFeed
            rows={rows}
            activeIndex={activeIndex}
            onSelect={(i) => seek(rows[i].t_start_sec)}
            generating={generating}
            autoFollow={isPlaying}
          />
        </div>

        {rows.length > 0 && (
          <div className="mb-8">
            <TotalsPanel rows={rows} />
          </div>
        )}

        {isDone && flagsQuery.data && <ReviewFlagPanel jobId={jobId} flags={flagsQuery.data} />}
      </div>
    </div>
  );
}

