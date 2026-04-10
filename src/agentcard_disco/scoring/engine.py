"""
Scoring engine — orchestrates all analyzers into a single ScoreReport.

Tier 1 (always, no dependencies):
    metadata_richness      0-30 pts
    semantic_specificity   0-30 pts
    search_alignment       0-20 pts
    completeness           0-20 pts
    ─────────────────────────────────
    Tier 1 total:          0-100 pts   (deterministic, offline, instant)

Tier 2 (opt-in via --deep, requires OPENAI_API_KEY):
    ai_quality             0-20 pts   (AI-assisted, reads from .env)

When --deep is used the raw totals become 0-120 pts but percentage and
grade are still normalised over the full max_total — so the A–F scale
is consistent whether or not AI analysis is enabled.

Usage:
    from agentcard_disco.scoring.engine import score
    from agentcard_disco.parser import load

    card = load("agent-card.json")

    report       = score(card, source="agent-card.json")           # Tier 1
    deep_report  = score(card, source="agent-card.json", deep=True) # Tier 1 + 2
"""

from __future__ import annotations

import os
import pathlib

from agentcard_disco.models import AgentCard
from agentcard_disco.scoring import (
    completeness,
    metadata_richness,
    search_alignment,
    semantic_specificity,
)
from agentcard_disco.scoring.result import ScoreReport


def score(
    card: AgentCard,
    *,
    source: str = "<unknown>",
    deep: bool = False,
) -> ScoreReport:
    """
    Run all scoring analyzers against a validated AgentCard.

    Args:
        card:   Validated AgentCard instance (from the parser).
        source: File path or URL the card was loaded from (display only).
        deep:   When True, also runs the Tier 2 AI quality analyzer.
                Automatically loads GEMINI_API_KEY from .env if present.

    Returns:
        ScoreReport aggregating all dimension results.
    """
    if deep:
        _load_dotenv()

    # ── Tier 1: heuristic analyzers (always run) ───────────────────────────
    dimensions = [
        metadata_richness.analyze(card),     # 0-30 pts
        semantic_specificity.analyze(card),  # 0-30 pts
        search_alignment.analyze(card),      # 0-20 pts
        completeness.analyze(card),          # 0-20 pts
    ]

    # ── Tier 2: AI quality analyzer (--deep only) ──────────────────────────
    if deep:
        from agentcard_disco.scoring import ai_quality  # lazy import
        dimensions.append(ai_quality.analyze(card))     # 0-20 pts

    return ScoreReport(
        card_name=card.name,
        source=source,
        dimensions=dimensions,
        ai_enhanced=deep,
    )


# ── .env loader ────────────────────────────────────────────────────────────

def _load_dotenv() -> None:
    """
    Load variables from a .env file into os.environ (no-op if already set).

    Search order — stops at the first .env found:
      1. .env in the current working directory
      2. .env in the project root (detected via src-layout path from this file)

    Uses python-dotenv when available; falls back to a minimal built-in
    parser so the tool never hard-fails when python-dotenv isn't installed.
    """
    candidates = [
        pathlib.Path.cwd() / ".env",
        # src/agentcard_disco/scoring/engine.py → go up 4 levels to project root
        pathlib.Path(__file__).parents[3] / ".env",
    ]
    env_path = next((p for p in candidates if p.exists()), None)
    if env_path is None:
        return

    # Try python-dotenv first
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=env_path, override=False)
        return
    except ImportError:
        pass

    # Fallback: minimal KEY=value parser
    try:
        with open(env_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key   = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        pass
