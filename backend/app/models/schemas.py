"""Core data contracts that flow between pipeline stages.

Stage 3 (pure CV, no model call) produces MotionEvents -- an objective
hand/object/machine signal. Stage 4 consumes those alongside the video to
produce Segment (perception only). Stage 5 produces Classification
(structured, schema-constrained model output -- never free text, never a
TMU value). Stage 6 (pure code) combines Segment + Classification into a
MostRow, which Stage 7 writes into the Excel template.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.config.most_tables import DataCard, load_most_tables
from app.config.taxonomy import load_taxonomy

OnlineOfflineMode = Literal["ONLINE", "OFFLINE", "MACHINE AUTO"]


class MotionEvent(BaseModel):
    """Stage 3 (CV tracking) output -- an objective, model-free signal built
    from MediaPipe hand/pose landmarks and zero-shot object detection.
    distance_px is pixel-space, not real-world cm: no camera calibration/
    homography exists yet (that's Phase 2's calibration sub-step), so this
    is deliberately not converted to a fabricated real-world unit."""

    t_start_sec: float
    t_end_sec: float
    hand: Literal["L", "R"]
    action: Literal["MOVE", "GRASP", "HOLD", "RELEASE"]
    object: str | None = None
    distance_px: float
    machine_state: Literal["IDLE", "ACTUATING", "UNKNOWN"]


class Segment(BaseModel):
    """Stage 4 (VLM segmentation) output -- perception only, no classification."""

    segment_id: int
    source_video_uri: str
    t_start_sec: float
    t_end_sec: float
    description: str = Field(min_length=1)
    human_movement_state: str = "MOVE"
    machine_state: str = "IDLE"
    model_version: str
    prompt_version: str


class Classification(BaseModel):
    """Stage 5 (structured VLM classification) output.

    param_values are index digits (or, for PT, raw seconds) chosen ONLY from
    the enumerated values in most_tables.json -- never invented by the model.
    muda_ref must be one of the refs enumerated in taxonomy.json -- never a
    free-text category.
    """

    data_card: DataCard
    param_values: list[int]
    muda_ref: int
    freq: int = 1
    online_offline_mode: OnlineOfflineMode = "ONLINE"
    operator: int = 1
    confidence: float = Field(ge=0.0, le=1.0)
    model_version: str
    prompt_version: str

    @field_validator("param_values")
    @classmethod
    def _non_empty(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("param_values must not be empty")
        return v

    def validate_against_tables(self) -> None:
        """Raise if this classification uses any value outside the fixed,
        enumerated MOST tables or taxonomy -- the hard guardrail that no
        model call may invent a parameter value or a category."""
        tables = load_most_tables()
        model = tables.sequence_models[self.data_card]

        if len(self.param_values) != len(model.parameters):
            raise ValueError(
                f"{self.data_card} expects {len(model.parameters)} parameter "
                f"values, got {len(self.param_values)}"
            )

        if self.data_card != "PT":
            for position, value in enumerate(self.param_values):
                allowed = tables.allowed_indices_for(self.data_card, position)
                if value not in allowed:
                    label = model.parameter_labels[position]
                    raise ValueError(
                        f"{label} index {value} is not in the enumerated set "
                        f"{allowed} for data card {self.data_card}"
                    )

        taxonomy = load_taxonomy()
        if self.muda_ref not in taxonomy.valid_refs():
            raise ValueError(
                f"muda_ref {self.muda_ref} is not in the enumerated taxonomy "
                f"(valid refs: {taxonomy.valid_refs()})"
            )


class ReviewFlag(BaseModel):
    """Raised whenever Stage 5 output cannot be trusted to publish
    unattended -- either it failed hard validation against the fixed tables,
    or its confidence fell below the mandatory-review threshold. Stage 8
    (Human Review) must clear every flag before a study is finalized;
    nothing flagged is silently guessed through."""

    segment_id: int
    reason: str
    confidence: float | None = None


class MostRow(BaseModel):
    """One fully-resolved row of Sheet 1 ('MOST Analysis'), ready to write."""

    s_no: int
    station_no: str = ""
    activity_no: str = ""
    activity_description: str
    data_card: DataCard
    param_values: list[int]
    most_code: str
    freq: int
    tmu: float
    elemental_description: str
    operator: int
    muda_ref: int
    total_time_sec: float
    online_offline_mode: OnlineOfflineMode
    va_sec: float
    nvan_sec: float
    sva_sec: float
    nva_sec: float
    category: str

    source_video_uri: str
    t_start_sec: float
    t_end_sec: float
    segment_model_version: str
    segment_prompt_version: str
    classification_model_version: str
    classification_prompt_version: str
    confidence: float
    human_corrected: bool = False

    # 4 new reporting fields
    activity_movement_details: str = ""
    activity_duration_sec: float = 0.0
    activity_timeline: str = ""
    uppercase_elemental_description: str = ""

