"""FastAPI REST Service Layer (Roadmap Item 3).

Exposes full REST API for video upload, automated MOST pipeline analysis execution,
job status tracking, human review flag clearance, and Excel report downloading.
"""
from __future__ import annotations

import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI, BackgroundTasks, UploadFile, File, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from fastapi.middleware.cors import CORSMiddleware
from app.models.schemas import Classification, MostRow, ReviewFlag, Segment
from app.pipeline.stage8_human_review import HumanReviewEngine
from app.pipeline.stage7_excel_writer import write_most_analysis_workbook
from app.pipeline.stage2_preprocessing import blur_faces
from app.pipeline.stage3_cv_tracking import CVTracker
from app.pipeline.stage4_segmentation import segment_video
from app.pipeline.stage5_classification import classify_segments
from app.pipeline.stage6_tmu_engine import build_most_row
from app.services.gemini_client import GeminiClient

app = FastAPI(
    title="MOST Factory Video Analysis API",
    description="Automated time-and-motion study API using computer vision and Gemini VLM.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ROOT_DIR = Path(__file__).parent.parent.parent
UPLOAD_DIR = ROOT_DIR / "data" / "uploads"
TEMPLATE_PATH = ROOT_DIR / "data" / "templates" / "most_analysis_template.xlsx"
SAMPLE_VIDEO_PATH = ROOT_DIR / "data" / "samples" / "assy_with_press_operation.mp4"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MANUAL_SEC_PER_MOTION = 180

# In-memory job store with disk-backed JSON persistence
JOBS: Dict[str, Dict[str, Any]] = {}
JOBS_DB_PATH = UPLOAD_DIR / "jobs_db.json"


def _save_jobs_to_disk() -> None:
    """Persist jobs state and rows to disk so data survives server restarts."""
    try:
        data = {}
        for j_id, job in JOBS.items():
            engine: HumanReviewEngine | None = job.get("review_engine")
            rows = engine.get_finalized_rows() if engine else job.get("rows", [])
            segments = job.get("segments", [])
            flags = engine.get_pending_flags() if engine else job.get("flags", [])

            data[j_id] = {
                "status": job.get("status"),
                "phase": job.get("phase"),
                "raw_video_path": str(job.get("raw_video_path")) if job.get("raw_video_path") else None,
                "output_excel_path": str(job.get("output_excel_path")) if job.get("output_excel_path") else None,
                "activity_description": job.get("activity_description", ""),
                "station_no": job.get("station_no", ""),
                "activity_no": job.get("activity_no", ""),
                "error": job.get("error"),
                "elapsed_sec": job.get("elapsed_sec"),
                "estimated_manual_sec": job.get("estimated_manual_sec"),
                "rows": [r.model_dump() for r in rows],
                "segments": [s.model_dump() for s in segments],
                "flags": [f.model_dump() for f in flags],
            }

        tmp_path = JOBS_DB_PATH.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp_path.replace(JOBS_DB_PATH)
    except Exception as e:
        print(f"Warning: Failed to persist jobs to disk: {e}")


def _load_jobs_from_disk() -> None:
    """Load persisted jobs from disk into JOBS dictionary on startup."""
    if not JOBS_DB_PATH.exists():
        return
    try:
        data = json.loads(JOBS_DB_PATH.read_text(encoding="utf-8"))
        for j_id, item in data.items():
            raw_video = Path(item["raw_video_path"]) if item.get("raw_video_path") else None
            excel_path = Path(item["output_excel_path"]) if item.get("output_excel_path") else None

            rows = [MostRow(**r) for r in item.get("rows", [])]
            segments = [Segment(**s) for s in item.get("segments", [])]
            flags = [ReviewFlag(**f) for f in item.get("flags", [])]

            engine = HumanReviewEngine(rows, segments, flags) if (rows or segments or flags) else None

            JOBS[j_id] = {
                "status": item.get("status", "COMPLETED"),
                "phase": item.get("phase", "COMPLETED"),
                "raw_video_path": raw_video,
                "output_excel_path": excel_path,
                "activity_description": item.get("activity_description", ""),
                "station_no": item.get("station_no", ""),
                "activity_no": item.get("activity_no", ""),
                "error": item.get("error"),
                "elapsed_sec": item.get("elapsed_sec", 30.0),
                "estimated_manual_sec": item.get("estimated_manual_sec"),
                "rows": rows,
                "segments": segments,
                "flags": flags,
                "review_engine": engine,
                "excel_path": excel_path,
            }
    except Exception as e:
        print(f"Warning: Failed to load jobs from disk: {e}")


_load_jobs_from_disk()



class JobStatusResponse(BaseModel):
    job_id: str
    status: str  # "QUEUED", "PROCESSING", "COMPLETED", "FAILED"
    phase: str = "QUEUED"
    row_count: int = 0
    flag_count: int = 0
    error: str | None = None
    elapsed_sec: float | None = None
    estimated_manual_sec: int | None = None


class ReviewSubmission(BaseModel):
    segment_id: int
    data_card: str
    param_values: list[int]
    muda_ref: int
    activity_description: str = ""
    freq: int = 1


def _create_job(
    background_tasks: BackgroundTasks,
    job_id: str,
    raw_video_path: Path,
    activity_description: str,
    station_no: str,
    activity_no: str,
) -> str:
    output_excel_path = UPLOAD_DIR / f"{job_id}_most_analysis.xlsx"

    JOBS[job_id] = {
        "status": "QUEUED",
        "phase": "QUEUED",
        "raw_video_path": raw_video_path,
        "output_excel_path": output_excel_path,
        "activity_description": activity_description,
        "station_no": station_no,
        "activity_no": activity_no,
    }
    _save_jobs_to_disk()

    background_tasks.add_task(
        _process_video_job,
        job_id,
        raw_video_path,
        output_excel_path,
        activity_description,
        station_no,
        activity_no,
    )
    return job_id


def _process_video_job(
    job_id: str,
    raw_video_path: Path,
    output_excel_path: Path,
    activity_desc: str,
    station_no: str = "",
    activity_no: str = "",
) -> None:
    try:
        JOBS[job_id]["status"] = "PROCESSING"
        JOBS[job_id]["started_at"] = time.monotonic()
        _save_jobs_to_disk()

        # 1. Mandatory face blur pass
        JOBS[job_id]["phase"] = "PREPROCESSING"
        _save_jobs_to_disk()
        blurred_path = UPLOAD_DIR / f"_blurred_{raw_video_path.name}"
        blur_faces(raw_video_path, blurred_path)

        # 2. Stage 3: CV tracking — produces objective hand-state timing events
        JOBS[job_id]["phase"] = "PREPROCESSING"
        try:
            tracker = CVTracker(sample_fps=2.0)
            motion_events = tracker.build_motion_event_stream(blurred_path)
        except Exception:
            motion_events = None  # non-fatal: Stage 4 degrades gracefully without events

        # 3. Gemini Client & upload
        JOBS[job_id]["phase"] = "UPLOADING"
        _save_jobs_to_disk()
        client = GeminiClient()
        uploaded_video = client.upload_video(blurred_path)

        # 4. VLM Segmentation
        JOBS[job_id]["phase"] = "SEGMENTING"
        _save_jobs_to_disk()
        segments = segment_video(client, uploaded_video, str(raw_video_path), motion_events=motion_events)

        # 4. Structured Classification
        JOBS[job_id]["phase"] = "CLASSIFYING"
        _save_jobs_to_disk()
        classifications, review_flags = classify_segments(client, uploaded_video, segments)

        # 5. Deterministic TMU Engine
        JOBS[job_id]["phase"] = "FINALIZING"
        _save_jobs_to_disk()
        rows: list[MostRow] = []
        for i, seg in enumerate(segments):
            cls = classifications.get(seg.segment_id)
            if cls is not None:
                r = build_most_row(seg, cls, s_no=i + 1, activity_description=activity_desc)
                if station_no:
                    r.station_no = station_no
                if activity_no:
                    r.activity_no = activity_no
                rows.append(r)

        # 6. Write Excel
        write_most_analysis_workbook(rows, TEMPLATE_PATH, output_excel_path, activity_desc)

        # Store results
        engine = HumanReviewEngine(rows, segments, review_flags)
        JOBS[job_id]["status"] = "COMPLETED"
        JOBS[job_id]["phase"] = "COMPLETED"
        JOBS[job_id]["completed_at"] = time.monotonic()
        JOBS[job_id]["rows"] = rows
        JOBS[job_id]["segments"] = segments
        JOBS[job_id]["flags"] = review_flags
        JOBS[job_id]["review_engine"] = engine
        JOBS[job_id]["excel_path"] = output_excel_path
        _save_jobs_to_disk()
    except Exception as e:
        JOBS[job_id]["status"] = "FAILED"
        JOBS[job_id]["phase"] = "FAILED"
        JOBS[job_id]["error"] = str(e)
        _save_jobs_to_disk()



@app.post("/api/v1/analyze", response_model=JobStatusResponse)
async def analyze_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    activity_description: str = "ASSY WITH PRESS OPERATION",
    station_no: str = "",
    activity_no: str = "",
):
    """Upload a factory floor video clip to launch automated MOST study analysis."""
    job_id = str(uuid.uuid4())
    raw_video_path = UPLOAD_DIR / f"{job_id}_{file.filename}"

    with open(raw_video_path, "wb") as f:
        content = await file.read()
        f.write(content)

    _create_job(background_tasks, job_id, raw_video_path, activity_description, station_no, activity_no)
    return JobStatusResponse(job_id=job_id, status="QUEUED")


@app.post("/api/v1/analyze/sample", response_model=JobStatusResponse)
async def analyze_sample_video(
    background_tasks: BackgroundTasks,
    activity_description: str = "ASSY WITH PRESS OPERATION",
    station_no: str = "",
    activity_no: str = "",
):
    """Runs the pipeline against a bundled sample video."""
    sample_path = ROOT_DIR / "data" / "samples" / "assy_with_press_operation.mp4"
    if not sample_path.exists():
        # Fallback to kit video if available
        sample_path = Path(r"C:\Users\ipate\Downloads\kit.mp4")
    if not sample_path.exists():
        raise HTTPException(status_code=404, detail="Sample video not available on this server")

    job_id = str(uuid.uuid4())
    raw_video_path = UPLOAD_DIR / f"{job_id}_sample.mp4"
    shutil.copy(sample_path, raw_video_path)

    _create_job(background_tasks, job_id, raw_video_path, activity_description, station_no, activity_no)
    return JobStatusResponse(job_id=job_id, status="QUEUED")


@app.post("/api/v1/analyze/demo", response_model=JobStatusResponse)
async def analyze_demo_video(
    activity_description: str = "KIT ASSEMBLY OPERATION",
    station_no: str = "ST-01",
    activity_no: str = "A-101",
):
    """Instantly generates a pre-analyzed demo job with complete MOST rows and Excel report."""
    sample_path = Path(r"C:\Users\ipate\Downloads\kit.mp4")
    if not sample_path.exists():
        sample_path = ROOT_DIR / "data" / "samples" / "assy_with_press_operation.mp4"

    job_id = str(uuid.uuid4())
    raw_video_path = UPLOAD_DIR / f"{job_id}_demo.mp4"
    if sample_path.exists():
        shutil.copy(sample_path, raw_video_path)

    output_excel_path = UPLOAD_DIR / f"{job_id}_most_analysis.xlsx"

    # Pre-packaged motion sequence for demo video
    motion_defs = [
        (0.0, 5.2, "REACH AND GRASP PARTS KIT FROM BIN", "G", [1, 0, 1, 1, 0, 1, 0], 35, 1, "WITHIN REACH, GRASP THE FIXTURE"),
        (5.2, 12.8, "MOVE PARTS TO WORKSTATION TABLE", "G", [1, 0, 3, 1, 0, 1, 0], 0, 1, "MOVE PARTS TO FIXTURE LOCATION"),
        (12.8, 22.0, "ALIGN AND POSITION COMPONENTS INTO JIG", "C", [1, 1, 1, 1, 0, 0, 0], 0, 1, "POSITION COMPONENT IN JIG"),
        (22.0, 31.5, "ACTUATE PRESS CONTROL LEVER", "C", [1, 1, 1, 1, 0, 0, 0], 50, 1, "ACTUATE PRESS CONTROL LEVER"),
        (31.5, 42.1, "INSPECT FASTENER ALIGNMENT AND FIT", "G", [1, 0, 1, 1, 0, 1, 0], 40, 1, "INSPECT ALIGNMENT AND FIT"),
        (42.1, 54.6, "GRASP SUB-ASSEMBLY CONNECTOR", "G", [1, 0, 1, 1, 0, 1, 0], 35, 1, "GRASP SUB-ASSEMBLY CONNECTOR"),
        (54.6, 68.0, "FASTEN SCREWS WITH ELECTRIC DRIVER", "C", [1, 1, 1, 1, 0, 0, 0], 50, 1, "FASTEN SCREWS WITH ELECTRIC DRIVER"),
        (68.0, 81.4, "REMOVE COMPLETED KIT FROM FIXTURE", "G", [1, 0, 1, 1, 0, 1, 0], 35, 1, "REMOVE COMPLETED KIT FROM FIXTURE"),
        (81.4, 96.2, "TRANSFER FINISHED ASSEMBLY TO TRAY", "G", [1, 0, 3, 1, 0, 1, 0], 0, 1, "TRANSFER FINISHED ASSEMBLY TO TRAY"),
        (96.2, 112.0, "RETURN HANDS TO NEUTRAL READY POSITION", "G", [1, 0, 1, 1, 0, 1, 0], 35, 1, "RETURN HANDS TO NEUTRAL READY POSITION"),
    ]

    segments = []
    rows = []
    flags = []

    for i, (t0, t1, desc, card, params, muda, freq, upper_desc) in enumerate(motion_defs):
        seg = Segment(
            segment_id=i + 1,
            source_video_uri=str(raw_video_path),
            t_start_sec=t0,
            t_end_sec=t1,
            description=desc,
            human_movement_state="ACTUATING" if card in ("A", "P") else "REACHING",
            machine_state="ACTUATING" if card == "A" else "IDLE",
            model_version="demo-v1",
            prompt_version="demo-v1",
        )
        cls = Classification(
            data_card=card,
            param_values=params,
            muda_ref=muda,
            freq=freq,
            confidence=0.95 if card != "P" else 0.72,
            model_version="demo-v1",
            prompt_version="demo-v1",
        )
        r = build_most_row(seg, cls, s_no=i + 1, activity_description=activity_description)
        r.station_no = station_no
        r.activity_no = activity_no
        segments.append(seg)
        rows.append(r)

        if cls.confidence < 0.8:
            flags.append(
                ReviewFlag(
                    segment_id=i + 1,
                    reason=f"Low confidence ({cls.confidence*100:.0f}%) on classification card {card}",
                    suggested_card=card,
                    suggested_params=params,
                )
            )

    write_most_analysis_workbook(rows, TEMPLATE_PATH, output_excel_path, activity_description)
    engine = HumanReviewEngine(rows, segments, flags)

    JOBS[job_id] = {
        "status": "COMPLETED",
        "phase": "COMPLETED",
        "started_at": time.monotonic() - 30.0,
        "completed_at": time.monotonic(),
        "raw_video_path": raw_video_path,
        "output_excel_path": output_excel_path,
        "activity_description": activity_description,
        "station_no": station_no,
        "activity_no": activity_no,
        "rows": rows,
        "segments": segments,
        "flags": flags,
        "review_engine": engine,
        "excel_path": output_excel_path,
    }
    _save_jobs_to_disk()

    return JobStatusResponse(
        job_id=job_id,
        status="COMPLETED",
        phase="COMPLETED",
        row_count=len(rows),
        flag_count=len(flags),
        elapsed_sec=30.0,
        estimated_manual_sec=len(rows) * MANUAL_SEC_PER_MOTION,
    )


@app.get("/api/v1/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """Retrieve job processing status and summary metrics."""
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    engine: HumanReviewEngine | None = job.get("review_engine")
    rows = engine.get_finalized_rows() if engine else job.get("rows", [])
    flag_count = len(engine.get_pending_flags()) if engine else len(job.get("flags", []))

    started_at = job.get("started_at")
    elapsed_sec = None
    if started_at is not None:
        end = job.get("completed_at", time.monotonic())
        elapsed_sec = round(end - started_at, 1)

    return JobStatusResponse(
        job_id=job_id,
        status=job["status"],
        phase=job.get("phase", job["status"]),
        row_count=len(rows),
        flag_count=flag_count,
        error=job.get("error"),
        elapsed_sec=elapsed_sec,
        estimated_manual_sec=len(rows) * MANUAL_SEC_PER_MOTION if rows else None,
    )


@app.get("/api/v1/jobs/{job_id}/rows")
async def get_job_rows(job_id: str):
    """Returns whatever MostRow data currently exists for this job, as JSON."""
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    engine: HumanReviewEngine | None = job.get("review_engine")
    rows: list[MostRow] = engine.get_finalized_rows() if engine else job.get("rows", [])
    return [r.model_dump() for r in sorted(rows, key=lambda r: r.s_no)]


_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")
_CHUNK_SIZE = 1024 * 1024


def _ranged_file_response(file_path: Path, range_header: str | None, media_type: str) -> StreamingResponse:
    file_size = file_path.stat().st_size
    start, end = 0, file_size - 1

    if range_header:
        match = _RANGE_RE.match(range_header)
        if match:
            if match.group(1):
                start = int(match.group(1))
            if match.group(2):
                end = int(match.group(2))

    start = max(0, start)
    end = min(file_size - 1, end)
    length = end - start + 1

    def iterfile():
        with open(file_path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(_CHUNK_SIZE, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
    }
    status_code = 206 if range_header else 200
    return StreamingResponse(iterfile(), status_code=status_code, headers=headers, media_type=media_type)


@app.get("/api/v1/jobs/{job_id}/video")
async def get_job_video(job_id: str, request: Request):
    """Streams the original uploaded video back with Range header support for seeking."""
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    video_path: Path = job.get("raw_video_path")
    if not video_path or not video_path.exists():
        raise HTTPException(status_code=404, detail="Video file missing")

    range_header = request.headers.get("range")
    return _ranged_file_response(video_path, range_header, "video/mp4")


@app.get("/api/v1/jobs/{job_id}/excel")
async def download_excel_report(job_id: str):
    """Download the finalized formatted Excel report deliverable."""
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "COMPLETED":
        raise HTTPException(status_code=400, detail=f"Job is in state {job['status']}")

    excel_path: Path = job["excel_path"]
    if not excel_path.exists():
        raise HTTPException(status_code=404, detail="Excel output file missing")

    return FileResponse(
        path=excel_path,
        filename=excel_path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.get("/api/v1/jobs/{job_id}/flags")
async def get_review_flags(job_id: str):
    """Get unresolved review flags requiring human engineer inspection."""
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    engine: HumanReviewEngine | None = job.get("review_engine")
    if not engine:
        return []
    return [f.model_dump() for f in engine.get_pending_flags()]


@app.post("/api/v1/jobs/{job_id}/review")
async def submit_human_review(job_id: str, review: ReviewSubmission):
    """Submit a human engineer correction for a flagged segment."""
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    engine: HumanReviewEngine | None = job.get("review_engine")
    if not engine:
        raise HTTPException(status_code=400, detail="Job has no active review engine")

    updated_row = engine.update_row_classification(
        segment_id=review.segment_id,
        data_card=review.data_card,
        param_values=review.param_values,
        muda_ref=review.muda_ref,
        activity_description=review.activity_description,
        freq=review.freq,
    )

    # Re-write excel with updated rows
    final_rows = engine.get_finalized_rows()
    write_most_analysis_workbook(
        final_rows,
        TEMPLATE_PATH,
        job["excel_path"],
        job["activity_description"],
    )
    _save_jobs_to_disk()

    return {"status": "SUCCESS", "updated_row": updated_row.model_dump()}


# Serve Production Frontend (if built)
from fastapi.staticfiles import StaticFiles
frontend_dist = ROOT_DIR / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        file_path = frontend_dist / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(frontend_dist / "index.html")
