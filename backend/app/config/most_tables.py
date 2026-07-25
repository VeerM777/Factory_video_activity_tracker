"""Loader for the versioned MOST sequence-model / index config.

UNVERIFIED placeholder data -- see most_tables.json's `status` field. The
sequence-model column layouts match the real template exactly (they must,
since Stage 7 writes into those exact columns); the per-parameter index
guidance is a placeholder pending MOST license confirmation.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

DataCard = Literal["G", "C", "T", "PT"]

_MOST_TABLES_PATH = Path(__file__).parent / "most_tables.json"


class SequenceModel(BaseModel):
    name: str
    columns: list[str]
    parameters: list[str]
    parameter_labels: list[str]


class ParameterIndexDefinition(BaseModel):
    name: str
    allowed_indices: list[int]
    guidance_unverified: str


class MostTables(BaseModel):
    version: str
    status: str
    tmu_conversion_factor_sec_per_tmu: float
    index_scale: list[int]
    sequence_models: dict[DataCard, SequenceModel]
    parameter_index_definitions: dict[str, ParameterIndexDefinition]

    def allowed_indices_for(self, data_card: DataCard, param_position: int) -> list[int]:
        """allowed index values for the Nth parameter (0-based) of a given data card."""
        model = self.sequence_models[data_card]
        if data_card == "PT":
            raise ValueError("Process Time takes raw seconds, not an enumerated index")
        param_key = model.parameters[param_position]
        return self.parameter_index_definitions[param_key].allowed_indices


@lru_cache
def load_most_tables() -> MostTables:
    raw = json.loads(_MOST_TABLES_PATH.read_text(encoding="utf-8"))
    return MostTables(**raw)
