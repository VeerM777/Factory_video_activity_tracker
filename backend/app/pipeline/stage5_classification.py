"""Stage 5 -- Structured MOST Classification.

A model call constrained to a JSON schema assigns the sequence model type,
per-parameter index values, and taxonomy ref -- all from fixed enumerated
sets, never free text. This module then re-validates every value against
the same fixed tables in code (Classification.validate_against_tables): a
model call proposes, code disposes. Anything that fails validation, or
whose confidence is below CONFIDENCE_THRESHOLD, is never silently used --
it comes back as a ReviewFlag for the mandatory Stage 8 human review gate.
"""
from __future__ import annotations

from google.genai import types

from app.config.most_tables import load_most_tables
from app.config.taxonomy import load_taxonomy
from app.models.schemas import Classification, ReviewFlag, Segment
from app.services.gemini_client import PROMPT_VERSION, GeminiClient, SegmentDraft

CONFIDENCE_THRESHOLD = 0.75


def classify_segments(
    client: GeminiClient, video: str | bytes | types.File, segments: list[Segment]
) -> tuple[dict[int, Classification], list[ReviewFlag]]:
    """Returns (segment_id -> Classification for segments that passed
    validation, review flags for everything that didn't or was low
    confidence). A segment_id missing from the first dict always has a
    corresponding flag in the second -- callers must not assume a row exists
    for every input segment."""
    most_tables = load_most_tables()
    taxonomy = load_taxonomy()

    draft_client_segments = [
        SegmentDraft(t_start_sec=s.t_start_sec, t_end_sec=s.t_end_sec, description=s.description)
        for s in segments
    ]
    drafts, model_version = client.classify_segments(
        video, draft_client_segments, most_tables, taxonomy
    )

    classifications: dict[int, Classification] = {}
    flags: list[ReviewFlag] = []

    drafts_by_index = {d.segment_index: d for d in drafts}
    for i, segment in enumerate(segments):
        draft = drafts_by_index.get(i)
        if draft is None:
            flags.append(ReviewFlag(segment_id=segment.segment_id, reason="no classification returned"))
            continue

        try:
            classification = Classification(
                data_card=draft.data_card,
                param_values=draft.param_values,
                muda_ref=draft.muda_ref,
                freq=draft.freq,
                online_offline_mode=draft.online_offline_mode,
                operator=draft.operator,
                confidence=draft.confidence,
                model_version=model_version,
                prompt_version=PROMPT_VERSION,
            )
            classification.validate_against_tables()
        except ValueError as e:
            flags.append(ReviewFlag(segment_id=segment.segment_id, reason=str(e), confidence=draft.confidence))
            continue

        if classification.confidence < CONFIDENCE_THRESHOLD:
            flags.append(
                ReviewFlag(
                    segment_id=segment.segment_id,
                    reason=f"confidence {classification.confidence:.2f} below threshold {CONFIDENCE_THRESHOLD}",
                    confidence=classification.confidence,
                )
            )
            continue

        classifications[segment.segment_id] = classification

    return classifications, flags
