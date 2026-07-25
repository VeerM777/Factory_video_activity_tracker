// Mirrors backend/app/models/schemas.py and main.py response models exactly.
// Keep in sync by hand -- no codegen wired up yet.

export type JobPhase =
  | "QUEUED"
  | "PREPROCESSING"
  | "UPLOADING"
  | "SEGMENTING"
  | "CLASSIFYING"
  | "FINALIZING"
  | "COMPLETED"
  | "FAILED";

export type JobStatusValue = "QUEUED" | "PROCESSING" | "COMPLETED" | "FAILED";

export interface JobStatusResponse {
  job_id: string;
  status: JobStatusValue;
  phase: JobPhase;
  row_count: number;
  flag_count: number;
  error: string | null;
  elapsed_sec: number | null;
  estimated_manual_sec: number | null;
}

export type DataCard = "G" | "C" | "T" | "PT";
export type OnlineOfflineMode = "ONLINE" | "OFFLINE" | "MACHINE AUTO";

export interface MostRow {
  s_no: number;
  station_no: string;
  activity_no: string;
  activity_description: string;
  data_card: DataCard;
  param_values: number[];
  most_code: string;
  freq: number;
  tmu: number;
  elemental_description: string;
  operator: number;
  muda_ref: number;
  total_time_sec: number;
  online_offline_mode: OnlineOfflineMode;
  va_sec: number;
  nvan_sec: number;
  sva_sec: number;
  nva_sec: number;
  category: string;

  source_video_uri: string;
  t_start_sec: number;
  t_end_sec: number;
  segment_model_version: string;
  segment_prompt_version: string;
  classification_model_version: string;
  classification_prompt_version: string;
  confidence: number;
  human_corrected: boolean;

  activity_movement_details: string;
  activity_duration_sec: number;
  activity_timeline: string;
}

export interface ReviewFlag {
  segment_id: number;
  reason: string;
  confidence: number | null;
  attempted_data_card: DataCard | null;
  attempted_param_values: number[] | null;
  attempted_muda_ref: number | null;
}

export type TaxonomyBucket = "VA" | "SVA" | "NVA-N" | "NVA" | "Noise";

export function bucketFor(row: MostRow): TaxonomyBucket {
  if (row.va_sec > 0) return "VA";
  if (row.sva_sec > 0) return "SVA";
  if (row.nvan_sec > 0) return "NVA-N";
  if (row.nva_sec > 0) return "NVA";
  return "Noise";
}
