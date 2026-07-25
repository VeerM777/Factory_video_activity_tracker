"""Stage 8 -- Human Review Interface & Flag Clearance Engine (Roadmap Item 4a).

Enables industrial engineers to inspect ReviewFlags, correct classifications/parameters,
mark rows as human_corrected=True, and re-trigger deterministic TMU calculation.
"""
from __future__ import annotations

from app.models.schemas import Classification, MostRow, ReviewFlag, Segment
from app.pipeline.stage6_tmu_engine import build_most_row


class HumanReviewEngine:
    def __init__(
        self,
        rows: list[MostRow],
        segments: list[Segment],
        review_flags: list[ReviewFlag],
    ) -> None:
        self.rows = {r.s_no: r for r in rows}
        self.segments = {s.segment_id: s for s in segments}
        self.flags = {f.segment_id: f for f in review_flags}

    def get_pending_flags(self) -> list[ReviewFlag]:
        """Returns all unresolved review flags requiring human attention."""
        return list(self.flags.values())

    def update_row_classification(
        self,
        segment_id: int,
        data_card: str,
        param_values: list[int],
        muda_ref: int,
        activity_description: str = "",
        freq: int = 1,
        online_offline_mode: str = "ONLINE",
        operator: int = 1,
    ) -> MostRow:
        """Applies a human correction to a row, re-validates against fixed MOST tables,
        re-computes TMU/times, and clears the review flag."""
        segment = self.segments.get(segment_id)
        if segment is None:
            raise KeyError(f"Segment ID {segment_id} not found")

        classification = Classification(
            data_card=data_card,  # type: ignore
            param_values=param_values,
            muda_ref=muda_ref,
            freq=freq,
            online_offline_mode=online_offline_mode,  # type: ignore
            operator=operator,
            confidence=1.0,  # Human verified
            model_version="human_expert",
            prompt_version="human_expert",
        )

        # Re-validate strictly against fixed MOST tables & taxonomy
        classification.validate_against_tables()

        s_no = segment_id + 1
        updated_row = build_most_row(
            segment=segment,
            classification=classification,
            s_no=s_no,
            activity_description=activity_description or segment.description,
        )
        updated_row.human_corrected = True

        self.rows[s_no] = updated_row
        self.flags.pop(segment_id, None)  # Clear flag

        return updated_row

    def resolve_all_clear(self) -> bool:
        """Returns True if all review flags have been cleared."""
        return len(self.flags) == 0

    def get_finalized_rows(self) -> list[MostRow]:
        """Returns sorted finalized rows ready for Excel output."""
        return [self.rows[k] for k in sorted(self.rows.keys())]
