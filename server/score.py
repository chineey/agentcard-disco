"""
server/score.py — scoring, comparison, and suggestion endpoints.

All routes import agentcard_disco directly; no scoring logic lives here.
The engine handles both Tier 1 (always) and Tier 2 / deep (when GEMINI_API_KEY
is set in the environment). This file just calls engine.score() and serialises
the result.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

# ── agentcard_disco imports ────────────────────────────────────────────────
from agentcard_disco.models import AgentCard          # for inline-dict validation
from agentcard_disco.parser import FetchError, ParseError, load  # URL / file loading
from agentcard_disco.reporting.exporters import to_json           # dataclass → dict
from agentcard_disco.scoring.engine import score as run_score     # the engine

from server.auth import limiter, verify_api_key

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class CardPayload(BaseModel):
    """Supply the card either as an inline JSON object OR a URL — not both."""
    card: Optional[dict[str, Any]] = Field(
        None,
        description="Inline AgentCard JSON object.",
    )
    url: Optional[str] = Field(
        None,
        description="http(s):// URL to fetch the AgentCard from.",
    )
    deep: bool = Field(
        False,
        description=(
            "Enable Tier-2 AI quality analysis (requires GEMINI_API_KEY "
            "in the server environment)."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "card": {
                    "name": "My Agent",
                    "description": "Summarises sales data from CSV files.",
                },
                "deep": False,
            }
        }
    }


class ComparePayload(BaseModel):
    card_a: Optional[dict[str, Any]] = None
    url_a: Optional[str] = None
    card_b: Optional[dict[str, Any]] = None
    url_b: Optional[str] = None
    deep: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_card(card: Optional[dict], url: Optional[str]) -> tuple[AgentCard, str]:
    """
    Return (parsed AgentCard, source label).

    - Inline dict  → validated directly via AgentCard.model_validate()
                     (load() only accepts strings, not dicts)
    - URL string   → fetched + validated via load()
    - Neither      → 422
    """
    if card is not None:
        try:
            return AgentCard.model_validate(card), "<inline>"
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid AgentCard: {exc}",
            )

    if url is not None:
        try:
            return load(url), url
        except FetchError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Could not fetch card from URL: {exc}",
            )
        except ParseError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Card at URL failed validation: {exc}",
            )

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Supply either 'card' (JSON object) or 'url' (string).",
    )


def _score_to_dict(agent_card: AgentCard, deep: bool, source: str) -> dict:
    """
    Run the scoring engine and return a plain dict.

    ScoreReport is a @dataclass (not Pydantic), so we serialise it through
    the package's own to_json() exporter — which is the canonical, stable
    serialisation path — then parse it back to a dict.

    When deep=True the engine's ai_quality analyzer fires automatically
    as long as GEMINI_API_KEY is present in the environment. If the key
    is missing, the engine returns 0 pts for that dimension with a clear
    failure message instead of crashing.
    """
    report = run_score(agent_card, source=source, deep=deep)
    return json.loads(to_json(report))


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

@router.get("/health", tags=["Meta"])
async def health():
    """Liveness check — no auth required."""
    return {"status": "ok", "service": "agentcard-disco-api"}


# ---------------------------------------------------------------------------
# POST /v1/score
# ---------------------------------------------------------------------------

@router.post("/score", tags=["Scoring"])
@limiter.limit("30/hour")
async def score_card(
    request: Request,
    payload: CardPayload,
    _key: dict = Depends(verify_api_key),
):
    """
    Score a single AgentCard and return the full report.

    Supply the card as an inline JSON object **or** a URL.
    Add `"deep": true` to enable Tier-2 AI quality analysis
    (requires `GEMINI_API_KEY` in the server environment).
    """
    agent_card, source = _resolve_card(payload.card, payload.url)
    return _score_to_dict(agent_card, payload.deep, source)


# ---------------------------------------------------------------------------
# POST /v1/compare
# ---------------------------------------------------------------------------

@router.post("/compare", tags=["Scoring"])
@limiter.limit("20/hour")
async def compare_cards(
    request: Request,
    payload: ComparePayload,
    _key: dict = Depends(verify_api_key),
):
    """
    Score two AgentCards and return both results plus a diff summary.

    Mix and match: card_a can be inline JSON while url_b is a URL, etc.
    """
    card_a, source_a = _resolve_card(payload.card_a, payload.url_a)
    card_b, source_b = _resolve_card(payload.card_b, payload.url_b)

    result_a = _score_to_dict(card_a, payload.deep, source_a)
    result_b = _score_to_dict(card_b, payload.deep, source_b)

    # Score lives at result["overall"]["score"] in the to_json() schema
    total_a = result_a.get("overall", {}).get("score", 0)
    total_b = result_b.get("overall", {}).get("score", 0)

    return {
        "card_a": result_a,
        "card_b": result_b,
        "diff": {
            "total_score_delta": round(total_b - total_a, 2),
            "winner": (
                "card_b" if total_b > total_a
                else "card_a" if total_a > total_b
                else "tie"
            ),
        },
    }


# ---------------------------------------------------------------------------
# POST /v1/suggest
# ---------------------------------------------------------------------------

@router.post("/suggest", tags=["Scoring"])
@limiter.limit("20/hour")
async def suggest_improvements(
    request: Request,
    payload: CardPayload,
    _key: dict = Depends(verify_api_key),
):
    """
    Score a card and return the full report with improvement suggestions
    surfaced at the top level for convenience.

    Suggestions are already inside the score report; this endpoint just
    promotes them to make them easier to consume without parsing the full
    report.
    """
    agent_card, source = _resolve_card(payload.card, payload.url)
    score_result = _score_to_dict(agent_card, payload.deep, source)

    return {
        "score": score_result,
        "suggestions": score_result.get("suggestions", []),
    }
