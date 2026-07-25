import type { JobStatusResponse, MostRow, ReviewFlag, DataCard } from "./types";

const BASE = "/api/v1";

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // response wasn't JSON -- keep statusText
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export interface AnalyzeMeta {
  activityDescription: string;
  stationNo?: string;
  activityNo?: string;
}

export async function analyzeVideo(file: File, meta: AnalyzeMeta): Promise<JobStatusResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("activity_description", meta.activityDescription);
  if (meta.stationNo) form.append("station_no", meta.stationNo);
  if (meta.activityNo) form.append("activity_no", meta.activityNo);
  const res = await fetch(`${BASE}/analyze`, { method: "POST", body: form });
  return handle<JobStatusResponse>(res);
}

export async function analyzeSampleVideo(meta: AnalyzeMeta): Promise<JobStatusResponse> {
  const params = new URLSearchParams({ activity_description: meta.activityDescription });
  if (meta.stationNo) params.set("station_no", meta.stationNo);
  if (meta.activityNo) params.set("activity_no", meta.activityNo);
  const res = await fetch(`${BASE}/analyze/demo?${params.toString()}`, { method: "POST" });
  return handle<JobStatusResponse>(res);
}

export async function getJobStatus(jobId: string): Promise<JobStatusResponse> {
  const res = await fetch(`${BASE}/jobs/${jobId}`);
  return handle<JobStatusResponse>(res);
}

export async function getJobRows(jobId: string): Promise<MostRow[]> {
  const res = await fetch(`${BASE}/jobs/${jobId}/rows`);
  return handle<MostRow[]>(res);
}

export async function getJobFlags(jobId: string): Promise<ReviewFlag[]> {
  const res = await fetch(`${BASE}/jobs/${jobId}/flags`);
  return handle<ReviewFlag[]>(res);
}

export function excelDownloadUrl(jobId: string): string {
  return `${BASE}/jobs/${jobId}/excel`;
}

export function videoUrl(jobId: string): string {
  return `${BASE}/jobs/${jobId}/video`;
}

export interface ReviewSubmission {
  segment_id: number;
  data_card: DataCard;
  param_values: number[];
  muda_ref: number;
  activity_description?: string;
  freq?: number;
}

export async function submitReview(jobId: string, review: ReviewSubmission) {
  const res = await fetch(`${BASE}/jobs/${jobId}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(review),
  });
  return handle<{ status: string; updated_row: MostRow }>(res);
}
