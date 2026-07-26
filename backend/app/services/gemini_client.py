"""Gemini client for Stages 4-5. Structured/constrained JSON output only --
no free-text parsing feeds a TMU value or a category anywhere in this
pipeline.

Two backends, toggled by GEMINI_USE_VERTEX (config lives in backend/.env,
gitignored -- copy .env.example and fill in your own values, never commit
real keys):

  GEMINI_USE_VERTEX=false (default while prototyping)
    Google AI Studio / Gemini Developer API -- free tier, no GCP project or
    billing account needed. Reads GEMINI_API_KEY.

  GEMINI_USE_VERTEX=true (production path)
    Vertex AI -- required for VPC-SC/CMEK/regional data residency. Reads
    GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION, and needs Application
    Default Credentials (gcloud auth application-default login) or a
    service account key via GOOGLE_APPLICATION_CREDENTIALS.

Either way: GEMINI_MODEL selects the model id (default: gemini-flash-latest --
gemini-2.5-pro and other pro-tier models return 429 quota-0 on the AI Studio
free tier as of 2026-07, verified against a live key; switch once billing
is enabled if flash-tier classification quality isn't sufficient).
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel

from app.config.most_tables import MostTables
from app.config.taxonomy import Taxonomy

load_dotenv()

PROMPT_VERSION = "v5"


class SegmentDraft(BaseModel):
    t_start_sec: float
    t_end_sec: float
    description: str
    human_movement_state: str = "MOVE"
    machine_state: str = "IDLE"


class SegmentationResponse(BaseModel):
    segments: list[SegmentDraft]


class ClassificationDraft(BaseModel):
    segment_index: int
    data_card: Literal["G", "C", "T", "PT"]
    param_values: list[int]
    muda_ref: int
    freq: int = 1
    online_offline_mode: Literal["ONLINE", "OFFLINE", "MACHINE AUTO"] = "ONLINE"
    operator: int = 1
    confidence: float


class ClassificationResponse(BaseModel):
    classifications: list[ClassificationDraft]


_SEGMENTATION_PROMPT = """You are assisting an industrial time-and-motion study. Watch this fixed-camera video of a workstation work cycle.

CRITICAL MICRO-MOTION SEGMENTATION RULE:
1. Segment ALL physical movements and actions occurring in the video, whether performed by a human operator, a robotic arm, a tool, or automated equipment.
2. Do NOT combine multiple micro-actions (e.g. reaching, grasping, lowering, positioning, pressing, releasing, retracting, returning). Every single micro-motion MUST last strictly between 1.0 second and 2.0 seconds maximum. NEVER output segments longer than 2.0 seconds.
3. For a 15-second video, you MUST produce roughly 8 to 10 distinct micro-activity segments (e.g. ~1.5s to 2.0s per segment).
4. Align segment start and end timestamps strictly with physical activity transitions.

RICH NATURAL HUMAN LANGUAGE DESCRIPTION RULE:
Every 'description' MUST be a detailed, rich natural human language sentence describing:
- The actor ("An operator", "Robotic arms", "The automated press mechanism")
- The specific movement ("reaching with pneumatic grippers", "grasping component", "lowering and positioning", "pressing and securing", "releasing and retracting", "returning to standby")
- The specific object or tool involved ("the workpiece", "the battery module frame", "the press fixture", "the pneumatic gripper")
- The workstation location context ("from the intake conveyor", "into the battery pack housing")

EXAMPLES OF RICH MICRO-MOTION DESCRIPTIONS (8-segment micro-breakdown for a 15s clip):
  "Robotic arms positioning battery modules over the automated guided vehicle" (t_start_sec: 0.0, t_end_sec: 1.5)
  "Robotic arms lowering battery modules down toward the battery pack housing" (t_start_sec: 1.5, t_end_sec: 3.5)
  "Robotic arms placing battery modules firmly into the compartments of the tray" (t_start_sec: 3.5, t_end_sec: 5.5)
  "Robotic arms releasing battery modules inside the tray and beginning to retract" (t_start_sec: 5.5, t_end_sec: 7.5)
  "Robotic arms raising away from the installed battery modules in the tray" (t_start_sec: 7.5, t_end_sec: 9.5)
  "Robotic arms shifting sideways and hovering over the adjacent component bin" (t_start_sec: 9.5, t_end_sec: 11.5)
  "Robotic arms lowering down to secure additional components onto the battery tray" (t_start_sec: 11.5, t_end_sec: 13.5)
  "Robotic arms lifting up and returning to their default standby positions above table" (t_start_sec: 13.5, t_end_sec: 15.0)

For each micro-activity segment, output:
  - t_start_sec, t_end_sec: exact micro-boundary timestamps in seconds (max 2.0s duration per segment)
  - description: rich, detailed natural human language sentence describing the action
  - human_movement_state: state of movement ("MOVE", "GRASP", "HOLD", "RELEASE")
  - machine_state: state of machine ("IDLE", "ACTUATING")

Order segments chronologically without gaps or overlapping intervals.
"""


def _format_motion_events(events: list) -> str:
    """Renders Stage 3's motion-event stream as compact text context for the
    segmentation prompt. Only t_start/t_end/hand/action are trustworthy
    (see stage3_cv_tracking's docstring on why `object` is usually None) --
    this is an objective timing signal to anchor boundaries to, not a
    description to copy."""
    action_phrase = {
        "GRASP": "hand begins holding something (grasp)",
        "RELEASE": "hand stops holding something (release)",
        "HOLD": "hand continues holding, still moving",
        "MOVE": "hand moving, not holding anything",
    }
    lines = [
        f"{e.t_start_sec:.2f}-{e.t_end_sec:.2f}s: {e.hand} {action_phrase.get(e.action, e.action)}"
        for e in events
    ]
    return "\n".join(lines)


_MOTION_EVENTS_PREAMBLE = """
Below is an OBJECTIVE hand-tracking signal computed directly from the video by
computer vision (MediaPipe hand landmarks) -- not a guess, not from a language model.
Each line is a moment where a hand's motion or grasp state changed. Treat these
timestamps as strong, trustworthy hints for where your segment boundaries should
fall -- a real elemental motion boundary (reach starts, grasp happens, release
happens) very often lines up with one of these transitions. Do not simply copy this
list as your segments (it has no descriptions and can be noisy); use it to anchor
the timing of the segments you write from watching the video.
"""


def _classification_prompt(most_tables: MostTables, taxonomy: Taxonomy) -> str:
    model_lines = []
    for card, model in most_tables.sequence_models.items():
        if card == "PT":
            model_lines.append(f'- "{card}" ({model.name}): single field, RAW SECONDS (not an index).')
            continue
        params = ", ".join(
            f"{label} [{most_tables.parameter_index_definitions[letter].name}, allowed indices "
            f"{most_tables.parameter_index_definitions[letter].allowed_indices}]"
            for letter, label in zip(model.parameters, model.parameter_labels)
        )
        model_lines.append(f'- "{card}" ({model.name}), {len(model.parameters)} values in order: {params}')

    taxonomy_lines = [f"{e.ref}: {e.description} ({e.classification})" for e in taxonomy.entries]

    return f"""You are the structured classification step of a MOST time-and-motion study.
You are given the same video and a list of already-segmented elemental motions
(index, start/end time, description).

Before classifying, look closely at what each tool/action actually DOES to the part --
not just what the tool looks like. A pen/syringe-shaped dispenser applying a visible
substance (glue, sealant, paint) onto the part is GLUING (ref 35) or PAINTING (ref 41),
not fastening/screwing (ref 42), even if it superficially resembles a powered
screwdriver. A rotating bit engaging and turning a screw head is fastening (ref 42).
Check for physical evidence in the frame -- residue, adhesive, or material appearing
on the part -- rather than assuming from the tool's silhouette alone.

For EACH segment, in the same order, choose:

1. data_card -- exactly one of: "G", "C", "T", "PT"
{chr(10).join(model_lines)}

   param_values must have exactly the right number of entries for the chosen
   data_card, in the order listed, and each value must be chosen ONLY from that
   parameter's allowed indices. Never invent a value outside the enumerated set.
   For "PT", param_values is a single-element list containing the raw seconds
   observed (a real number is fine, e.g. [4.5]).

2. muda_ref -- exactly one integer from this fixed taxonomy (never invent a
   category, never return free text):
{chr(10).join(taxonomy_lines)}

3. freq -- how many times this exact motion repeats in the cycle (usually 1).
4. online_offline_mode -- one of "ONLINE", "OFFLINE", "MACHINE AUTO".
5. operator -- operator count performing this motion (usually 1).
6. confidence -- your confidence in this classification, 0.0-1.0. Be honest and
   conservative; a low score here triggers mandatory human review rather than
   silently publishing a guess.

Return one classification per input segment, with segment_index matching the
segment's position (0-based) in the input list.
"""


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes")


class GeminiClient:
    def __init__(
        self,
        project: str | None = None,
        location: str | None = None,
        model: str | None = None,
        use_vertex: bool | None = None,
        api_key: str | None = None,
    ) -> None:
        self.use_vertex = use_vertex if use_vertex is not None else _env_flag("GEMINI_USE_VERTEX", False)
        self.model = model or os.environ.get("GEMINI_MODEL", "gemini-flash-latest")

        if self.use_vertex:
            self.project = project or os.environ["GOOGLE_CLOUD_PROJECT"]
            self.location = location or os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
            self.client = genai.Client(vertexai=True, project=self.project, location=self.location)
        else:
            # Google AI Studio / Gemini Developer API -- free tier, no GCP
            # project or billing account required.
            key = api_key or os.environ["GEMINI_API_KEY"]
            self.client = genai.Client(api_key=key)

    def upload_video(self, path: Path, poll_interval_sec: float = 3.0) -> types.File:
        """AI Studio / Developer API only. Uploads a local (already
        face-blurred) video via the Files API and waits for Gemini to finish
        processing it -- required before it can be referenced in a prompt.
        Preferred over inline bytes for anything beyond a tiny clip, since
        inline base64 payloads hit request-size limits well under typical
        work-cycle video sizes."""
        if self.use_vertex:
            raise NotImplementedError(
                "Vertex AI mode expects a gs:// URI -- upload the blurred video to "
                "your configured Cloud Storage bucket and pass that URI instead."
            )
        uploaded = self.client.files.upload(file=str(path))
        while uploaded.state and uploaded.state.name == "PROCESSING":
            time.sleep(poll_interval_sec)
            uploaded = self.client.files.get(name=uploaded.name)
        if uploaded.state and uploaded.state.name == "FAILED":
            raise RuntimeError(f"Gemini Files API failed to process {path}: {uploaded}")
        return uploaded

    @staticmethod
    def _video_part(video: str | bytes | types.File, mime_type: str) -> types.Part | types.File:
        """video is a gs:// URI (Vertex AI), an uploaded types.File (AI
        Studio Files API, see upload_video -- preferred for real clips), or
        raw bytes (inline upload, fine only for tiny clips)."""
        if isinstance(video, types.File):
            return video
        if isinstance(video, bytes):
            return types.Part.from_bytes(data=video, mime_type=mime_type)
        return types.Part.from_uri(file_uri=video, mime_type=mime_type)

    def _generate_content_with_retry(
        self,
        contents: list,
        config: types.GenerateContentConfig,
        max_retries: int = 5,
    ):
        # Valid active models on AI Studio / Vertex — ordered by free-tier quota:
        # gemini-2.0-flash: 1,500 req/day  ← primary, high quota
        # gemini-2.5-flash: 500 req/day    ← secondary
        # gemini-flash-latest (= gemini-3.6-flash): 20 req/day ← emergency fallback only
        valid_candidates = ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-flash-latest", "gemini-3.6-flash"]
        models_to_try = [self.model] if self.model in valid_candidates else []
        for alt_model in valid_candidates:
            if alt_model not in models_to_try:
                models_to_try.append(alt_model)

        last_exc = None
        for model_name in models_to_try:
            for attempt in range(max_retries):
                try:
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=config,
                    )
                    return response, model_name
                except Exception as e:
                    last_exc = e
                    err_str = str(e)
                    if "404" in err_str or "NOT_FOUND" in err_str:
                        # Model ID not available in this region/version, try next model candidate
                        break
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                        wait_sec = 2.0
                        time.sleep(wait_sec)
                    else:
                        time.sleep(1.0)
        raise last_exc

    def segment_video(
        self,
        video: str | bytes | types.File,
        mime_type: str = "video/mp4",
        motion_events: list | None = None,
    ) -> tuple[list[SegmentDraft], str]:
        """Stage 4. `video` must be an already face-blurred video (Stage 2
        output) -- this client never receives raw footage. `motion_events`
        (optional) is Stage 3's objective hand-tracking event stream --
        passed as text context to help the model land segment boundaries on
        real, measured hand-state transitions instead of estimating from
        video alone."""
        contents = [self._video_part(video, mime_type), _SEGMENTATION_PROMPT]
        if motion_events:
            contents.append(_MOTION_EVENTS_PREAMBLE + _format_motion_events(motion_events))

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SegmentationResponse,
        )
        response, used_model = self._generate_content_with_retry(contents, config)
        parsed = SegmentationResponse.model_validate_json(response.text)
        return parsed.segments, used_model

    def classify_segments(
        self,
        video: str | bytes | types.File,
        segments: list[SegmentDraft],
        most_tables: MostTables,
        taxonomy: Taxonomy,
        mime_type: str = "video/mp4",
    ) -> tuple[list[ClassificationDraft], str]:
        """Stage 5. Structured output only -- schema enumerates data_card and
        muda_ref; param_values are cross-checked against the fixed index
        tables again downstream (Classification.validate_against_tables)
        before any TMU math runs."""
        segment_listing = "\n".join(
            f"{i}: [{s.t_start_sec:.2f}s - {s.t_end_sec:.2f}s] {s.description}"
            for i, s in enumerate(segments)
        )
        contents = [
            _classification_prompt(most_tables, taxonomy),
            f"\nSegments:\n{segment_listing}",
        ]
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ClassificationResponse,
        )
        response, used_model = self._generate_content_with_retry(contents, config)
        parsed = ClassificationResponse.model_validate_json(response.text)
        return parsed.classifications, used_model
