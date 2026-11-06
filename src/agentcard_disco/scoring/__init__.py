"""Scoring engine and analyzers."""

from . import completeness, metadata_richness, search_alignment, semantic_specificity
from .engine import score
from .result import DimensionResult, Grade, ScoreReport, Suggestion

# ai_quality is NOT imported here at package load time — it is a lazy
# import inside engine.py, only when deep=True, so the `groq` package
# is never required for standard Tier 1 scoring.

__all__ = [
    "DimensionResult",
    "Grade",
    "ScoreReport",
    "Suggestion",
    "completeness",
    "metadata_richness",
    "score",
    "search_alignment",
    "semantic_specificity",
    # "ai_quality" is accessible as agentcard_disco.scoring.ai_quality
]
