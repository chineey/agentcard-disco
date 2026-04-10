"""Scoring engine and analyzers."""

from . import completeness, metadata_richness, search_alignment, semantic_specificity
from .engine import score
from .result import DimensionResult, Grade, ScoreReport, Suggestion

# ai_quality is NOT imported here at package load time — it is a lazy
# import inside engine.py, only when deep=True, so the `anthropic` package
# is never required for standard Tier 1 scoring.

__all__ = [
    "score",
    "ScoreReport",
    "DimensionResult",
    "Grade",
    "Suggestion",
    "metadata_richness",
    "semantic_specificity",
    "search_alignment",
    "completeness",
    # "ai_quality" is accessible as agentcard_disco.scoring.ai_quality
]
