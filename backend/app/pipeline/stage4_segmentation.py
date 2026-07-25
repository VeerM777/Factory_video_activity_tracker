"""Stage 4 -- VLM Segmentation.

Confirms/refines segment boundaries and writes a plain-language elemental
description per segment. Now consumes Stage 3's motion-event stream
(objective hand-tracking timing) alongside the video when available, per
the brief's own design ("using both the video and objective measurements --
not vision alone"); falls back to video-only if Stage 3 wasn't run.
"""
from __future__ import annotations

from google.genai import types

from app.models.schemas import MotionEvent, Segment
from app.services.gemini_client import PROMPT_VERSION, GeminiClient


def segment_video(
    client: GeminiClient,
    video: str | bytes | types.File,
    source_video_uri: str,
    motion_events: list[MotionEvent] | None = None,
) -> list[Segment]:
    """`video` is what actually gets sent to Gemini (a gs:// URI or raw
    bytes); `source_video_uri` is the stable audit reference recorded on
    every row regardless of how the video was transmitted."""
    drafts, model_version = client.segment_video(video, motion_events=motion_events)
    return [
        Segment(
            segment_id=i,
            source_video_uri=source_video_uri,
            t_start_sec=d.t_start_sec,
            t_end_sec=d.t_end_sec,
            description=d.description,
            human_movement_state=getattr(d, "human_movement_state", "MOVE"),
            machine_state=getattr(d, "machine_state", "IDLE"),
            model_version=model_version,
            prompt_version=PROMPT_VERSION,
        )
        for i, d in enumerate(drafts)
    ]
