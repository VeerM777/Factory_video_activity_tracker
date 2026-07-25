"""Phase 0 CLI: video in -> face-blur -> CV tracking -> segment -> classify
-> TMU -> Excel.

Requires backend/.env configured (GEMINI_API_KEY for the AI Studio free
tier, or GOOGLE_CLOUD_PROJECT + ADC for Vertex AI) before running -- this
script makes real Gemini calls, it is not a mock.

Usage:
    python scripts/run_phase0.py --video path/to/cycle.mp4 \\
        --output path/to/output.xlsx \\
        --activity-description "ASSY WITH PRESS OPERATION" \\
        [--ground-truth path/to/ground_truth.xlsx] \\
        [--skip-cv]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.schemas import MostRow
from app.pipeline.diff_report import build_diff_report
from app.pipeline.stage2_preprocessing import blur_faces
from app.pipeline.stage3_cv_tracking import CVTracker
from app.pipeline.stage4_segmentation import segment_video
from app.pipeline.stage5_classification import classify_segments
from app.pipeline.stage6_tmu_engine import build_most_row
from app.pipeline.stage7_excel_writer import write_most_analysis_workbook
from app.services.gemini_client import GeminiClient

ROOT = Path(__file__).parent.parent.parent
TEMPLATE_PATH = ROOT / "data" / "templates" / "most_analysis_template.xlsx"


def run(
    video_path: Path,
    output_path: Path,
    activity_description: str,
    ground_truth: Path | None,
    skip_cv: bool = False,
) -> None:
    print(f"[1/7] Ingest: {video_path}")
    if not video_path.exists():
        raise FileNotFoundError(video_path)

    print("[2/7] Preprocessing: mandatory face-blur pass")
    blurred_path = output_path.parent / f"_blurred_{video_path.name}"
    blur_faces(video_path, blurred_path)
    print(f"      blurred video written to {blurred_path} ({blurred_path.stat().st_size} bytes)")

    motion_events = None
    if not skip_cv:
        print("[3/7] Stage 3: CV tracking (hands/pose + zero-shot object detection)")
        tracker = CVTracker(sample_fps=4.0)
        motion_events = tracker.build_motion_event_stream(blurred_path)
        print(f"      {len(motion_events)} motion events detected")
    else:
        print("[3/7] Stage 3: skipped (--skip-cv)")

    client = GeminiClient()

    print("      uploading blurred video to Gemini (Files API)")
    uploaded_video = client.upload_video(blurred_path)
    print(f"      upload active: {uploaded_video.name}")

    print("[4/7] Stage 4: VLM segmentation")
    # source_video_uri is the stable audit reference recorded on every row;
    # uploaded_video is what's actually sent to Gemini.
    source_video_uri = str(video_path)
    segments = segment_video(client, uploaded_video, source_video_uri, motion_events=motion_events)
    print(f"      {len(segments)} segments found")

    print("[5/7] Stage 5: structured classification")
    classifications, review_flags = classify_segments(client, uploaded_video, segments)
    if review_flags:
        print(f"      WARNING: {len(review_flags)} segment(s) need mandatory human review:")
        for flag in review_flags:
            print(f"        segment {flag.segment_id}: {flag.reason}")

    print("[6/7] Stage 6: deterministic TMU engine")
    rows: list[MostRow] = []
    for i, segment in enumerate(segments):
        classification = classifications.get(segment.segment_id)
        if classification is None:
            continue  # flagged for review above; not published unattended
        rows.append(
            build_most_row(
                segment,
                classification,
                s_no=i + 1,
                activity_description=activity_description,
            )
        )

    print("[7/7] Stage 7: writing Excel")
    write_most_analysis_workbook(rows, TEMPLATE_PATH, output_path, activity_description)
    print(f"      wrote {len(rows)} rows to {output_path}")

    if review_flags:
        flags_path = output_path.with_suffix(".review_flags.json")
        flags_path.write_text(json.dumps([f.model_dump() for f in review_flags], indent=2))
        print(f"      {len(review_flags)} unresolved review flag(s) written to {flags_path}")

    if ground_truth:
        print("\n--- Phase 0 diff report vs. ground truth ---")
        report = build_diff_report(rows, ground_truth)
        print(report.summary_text())
        report_path = output_path.with_suffix(".diff_report.json")
        report_path.write_text(report.model_dump_json(indent=2))
        print(f"\nfull diff report written to {report_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--activity-description", default="ASSY WITH PRESS OPERATION")
    parser.add_argument("--ground-truth", type=Path, default=None)
    parser.add_argument("--skip-cv", action="store_true", help="skip Stage 3 CV tracking")
    args = parser.parse_args()

    run(args.video, args.output, args.activity_description, args.ground_truth, skip_cv=args.skip_cv)
