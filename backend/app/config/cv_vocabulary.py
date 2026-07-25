"""Loader for the versioned zero-shot object-detection vocabulary used by
Stage 3. Editable per station without any code change -- see cv_vocabulary.json.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

_CV_VOCAB_PATH = Path(__file__).parent / "cv_vocabulary.json"


class CVVocabulary(BaseModel):
    version: str
    object_queries: list[str]


@lru_cache
def load_cv_vocabulary() -> CVVocabulary:
    raw = json.loads(_CV_VOCAB_PATH.read_text(encoding="utf-8"))
    return CVVocabulary(version=raw["version"], object_queries=raw["object_queries"])
