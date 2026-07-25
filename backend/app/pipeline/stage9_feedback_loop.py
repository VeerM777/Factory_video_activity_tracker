"""Stage 9 -- Few-Shot Feedback Loop & Exemplar Storage (Roadmap Item 4b).

Persists human-corrected MostRow entries into a persistent feedback library
and formats high-confidence exemplars for injection into Stage 5 classification prompts.
"""
from __future__ import annotations

import json
from pathlib import Path
from pydantic import BaseModel

from app.models.schemas import MostRow

DEFAULT_LIBRARY_PATH = (
    Path(__file__).parent.parent.parent / "data" / "feedback_library.json"
)


class FeedbackExemplar(BaseModel):
    description: str
    data_card: str
    param_values: list[int]
    muda_ref: int
    category: str


class FeedbackLoopEngine:
    def __init__(self, library_path: Path = DEFAULT_LIBRARY_PATH) -> None:
        self.library_path = library_path
        self.library_path.parent.mkdir(parents=True, exist_ok=True)
        self.exemplars: list[FeedbackExemplar] = self._load()

    def _load(self) -> list[FeedbackExemplar]:
        if not self.library_path.exists():
            return []
        try:
            raw = json.loads(self.library_path.read_text())
            return [FeedbackExemplar.model_validate(item) for item in raw]
        except Exception:
            return []

    def record_correction(self, row: MostRow) -> None:
        """Stores a human-corrected row into the feedback library."""
        exemplar = FeedbackExemplar(
            description=row.elemental_description,
            data_card=row.data_card,
            param_values=row.param_values,
            muda_ref=row.muda_ref,
            category=row.category,
        )
        # Avoid exact duplicates
        if not any(
            e.description == exemplar.description
            and e.data_card == exemplar.data_card
            and e.param_values == exemplar.param_values
            for e in self.exemplars
        ):
            self.exemplars.append(exemplar)
            self._save()

    def _save(self) -> None:
        data = [e.model_dump() for e in self.exemplars]
        self.library_path.write_text(json.dumps(data, indent=2))

    def format_few_shot_prompt_context(self, max_examples: int = 5) -> str:
        """Renders saved human corrections as few-shot guidance for Stage 5 prompt."""
        if not self.exemplars:
            return ""
        lines = ["\nHUMAN-VERIFIED FEW-SHOT EXAMPLES (from previous engineer reviews):"]
        for ex in self.exemplars[:max_examples]:
            lines.append(
                f'- Description: "{ex.description}" -> DataCard: {ex.data_card}, '
                f"Params: {ex.param_values}, Ref: {ex.muda_ref} ({ex.category})"
            )
        return "\n".join(lines)
