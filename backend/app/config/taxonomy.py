"""Loader for the versioned VA/SVA/NVA/NVA-N/Noise taxonomy table.

This table is editable plant-level config, not application logic — see
taxonomy.json. Stage 5 (LLM classification) may only choose a `ref` that
exists in this table; Stage 6 (TMU engine) uses it to route each row's time
into the correct Y/Z/AA/AB column.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

Classification = Literal["VA", "SVA", "NVA", "NVA-N", "Noise"]

_TAXONOMY_PATH = Path(__file__).parent / "taxonomy.json"


class TaxonomyEntry(BaseModel):
    ref: int
    classification: Classification
    description: str
    legacy_ref: int | None = None


class Taxonomy(BaseModel):
    version: str
    entries: list[TaxonomyEntry]

    def by_ref(self, ref: int) -> TaxonomyEntry:
        for entry in self.entries:
            if entry.ref == ref:
                return entry
        raise KeyError(f"MUDA ref {ref} not found in taxonomy v{self.version}")

    def valid_refs(self) -> list[int]:
        return [e.ref for e in self.entries]


@lru_cache
def load_taxonomy() -> Taxonomy:
    raw = json.loads(_TAXONOMY_PATH.read_text(encoding="utf-8"))
    return Taxonomy(version=raw["version"], entries=raw["entries"])
