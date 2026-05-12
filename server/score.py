"""
server/score.py — scoring, comparison, and suggestion endpoints.

All routes import agentcard_disco directly; no scoring logic lives here.
Every request is logged to Supabase usage_logs as a background task.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from agentcard_disco.models import AgentCard
from agentcard_disco.parser import FetchError, ParseError, load
from agentcard_disco.reporting.exporters import to_json
from agentcard_disco.scoring.engine import score as run_score

from server.auth import limiter, verify_api_key
from server.usage import log_request

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class CardPayload(BaseModel):
    """Supply the card either as an inline JSON object OR a URL — not both."""
    card: Optional[dict[str, Any]] = Field(None, description="Inline AgentCard JSON object.")
    url: Optional[str] = Field(None, description="http(s):// URL to fetch the AgentCard from.")
    deep: bool = Field(False, description="Enable Tier-2 AI quality analysis (requires GEMINI_API_KEY).")

    model_config = {
        "json_schema_extra": {
            "example": {
                "card": {"name": "My Agent", "description": "Summarises sales data from CSV files."},
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
    report = run_score(agent_card, source=source, deep=deep)
    return json.loads(to_json(report))


# ---------------------------------------------------------------------------
# GET /health  (no auth, no logging)
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
    background_tasks: BackgroundTasks,
    key_row: dict = Depends(verify_api_key),
):
    """
    Score a single AgentCard and return the full report.

    Supply the card as an inline JSON object **or** a URL.
    Add `"deep": true` to enable Tier-2 AI quality analysis.
    """
    agent_card, source = _resolve_card(payload.card, payload.url)
    result = _score_to_dict(agent_card, payload.deep, source)

    background_tasks.add_task(
        log_request,
        key_hash=key_row.get("key_hash"),
        owner=key_row.get("owner"),
        endpoint="/v1/score",
        deep=payload.deep,
        status_code=200,
    )

    return result


# ---------------------------------------------------------------------------
# POST /v1/compare
# ---------------------------------------------------------------------------

@router.post("/compare", tags=["Scoring"])
@limiter.limit("20/hour")
async def compare_cards(
    request: Request,
    payload: ComparePayload,
    background_tasks: BackgroundTasks,
    key_row: dict = Depends(verify_api_key),
):
    """
    Score two AgentCards and return both results plus a diff summary.
    """
    card_a, source_a = _resolve_card(payload.card_a, payload.url_a)
    card_b, source_b = _resolve_card(payload.card_b, payload.url_b)

    result_a = _score_to_dict(card_a, payload.deep, source_a)
    result_b = _score_to_dict(card_b, payload.deep, source_b)

    total_a = result_a.get("overall", {}).get("score", 0)
    total_b = result_b.get("overall", {}).get("score", 0)

    background_tasks.add_task(
        log_request,
        key_hash=key_row.get("key_hash"),
        owner=key_row.get("owner"),
        endpoint="/v1/compare",
        deep=payload.deep,
        status_code=200,
    )

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
    background_tasks: BackgroundTasks,
    key_row: dict = Depends(verify_api_key),
):
    """
    Score a card and return the full report with improvement suggestions
    surfaced at the top level for convenience.
    """
    agent_card, source = _resolve_card(payload.card, payload.url)
    score_result = _score_to_dict(agent_card, payload.deep, source)

    background_tasks.add_task(
        log_request,
        key_hash=key_row.get("key_hash"),
        owner=key_row.get("owner"),
        endpoint="/v1/suggest",
        deep=payload.deep,
        status_code=200,
    )

    return {
        "score": score_result,
        "suggestions": score_result.get("suggestions", []),
    }