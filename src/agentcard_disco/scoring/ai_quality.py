"""
Analyzer 5 — AI Quality (0–20 points)   [Tier 2, requires --deep flag]

Architecture: "model observes, Python scores"
─────────────────────────────────────────────
The model is NEVER asked to produce a number. It is only asked to make
categorical yes/no/partial judgments about specific, narrow questions.
Python converts those judgments into points deterministically.

This eliminates score oscillation at the source: the same card will
produce the same categorical answers run-to-run, and the same answers
always produce the same points.

What the model evaluates (5 questions):
  Q1  Is the agent description specific and domain-focused?
  Q2  Are skill descriptions meaningfully distinct from each other?
  Q3  Do examples read like real user prompts?
  Q4  Is the card internally coherent (name ↔ skills ↔ tags)?
  Q5  Does the description explain inputs, outputs, or use-case?

Point mapping (Python, not the model):
  Q1  yes=6  partial=3  no=0
  Q2  yes=4  partial=2  no=0
  Q3  yes=4  partial=2  no=0    (0 if no examples exist)
  Q4  yes=3  partial=1  no=0
  Q5  yes=3  partial=1  no=0
  ──────────────────────────
  Max                    20 pts

Speed
─────
Single API call, ~200 token response, temperature=0.
Typical latency: 1–3 seconds on gemini-2.0-flash.

Environment / installation
──────────────────────────
  • Requires GEMINI_API_KEY in the environment (loaded from .env).
  • Requires the `google-genai` package:  pip install "agentcard-disco[deep]"
  • Any failure returns 0 pts with a clear warning — never crashes Tier 1.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from agentcard_disco.models import AgentCard
from agentcard_disco.scoring.result import DimensionResult, Suggestion

# ── Point tables (Python owns all arithmetic) ──────────────────────────────
_POINTS: dict[str, dict[str, float]] = {
    "description_specific":   {"yes": 6.0, "partial": 3.0, "no": 0.0},
    "skills_distinct":        {"yes": 4.0, "partial": 2.0, "no": 0.0},
    "examples_realistic":     {"yes": 4.0, "partial": 2.0, "no": 0.0},
    "card_coherent":          {"yes": 3.0, "partial": 1.0, "no": 0.0},
    "io_explained":           {"yes": 3.0, "partial": 1.0, "no": 0.0},
}

_TOTAL_MAX = sum(pts["yes"] for pts in _POINTS.values())   # 20.0

_DEFAULT_MODEL = "gemini-2.0-flash"

# ── Question definitions (human-readable, used in checks/failures output) ──
_QUESTION_LABELS: dict[str, str] = {
    "description_specific":  "Description is specific and domain-focused",
    "skills_distinct":       "Skill descriptions are meaningfully distinct",
    "examples_realistic":    "Examples read like real user prompts",
    "card_coherent":         "Card is internally coherent (name/skills/tags match)",
    "io_explained":          "Inputs, outputs, or use-case are explained",
}

# ── System prompt ──────────────────────────────────────────────────────────
# The model ONLY produces yes/no/partial + one-line reason.
# It never produces a number. No oscillation possible.
_SYSTEM_PROMPT = """\
You are auditing an A2A Agent Card for discoverability quality.
Answer exactly 5 questions about the card. For each question respond
with one of: "yes", "partial", or "no".

RULES:
- Respond with ONLY a valid JSON object. No preamble, no markdown, no extra text.
- Each answer must be exactly "yes", "partial", or "no" — nothing else.
- Each reason must be one sentence, under 20 words.
- Be strict. "partial" means genuinely mixed evidence, not "mostly good".

Response schema:
{
  "description_specific": {
    "answer": "yes" | "partial" | "no",
    "reason": "<one sentence under 20 words>"
  },
  "skills_distinct": {
    "answer": "yes" | "partial" | "no",
    "reason": "<one sentence under 20 words>"
  },
  "examples_realistic": {
    "answer": "yes" | "partial" | "no",
    "reason": "<one sentence under 20 words>"
  },
  "card_coherent": {
    "answer": "yes" | "partial" | "no",
    "reason": "<one sentence under 20 words>"
  },
  "io_explained": {
    "answer": "yes" | "partial" | "no",
    "reason": "<one sentence under 20 words>"
  }
}

Question definitions:

description_specific:
  yes     = uses domain terms, technology names, or precise verbs; no generic filler
  partial = mix of specific and vague language
  no      = dominated by generic words like "helps", "powerful", "various things"

skills_distinct:
  yes     = each skill description uses clearly different vocabulary and describes a different action
  partial = some overlap in wording or purpose between skills
  no      = skills read like copies of each other, or there is only one skill (answer "yes")
  NOTE: if there is only 1 skill, always answer "yes" for this question.

examples_realistic:
  yes     = examples are specific prompts a real user would type (e.g. "Summarise sales_q3.csv by region")
  partial = some examples are realistic, others are vague (e.g. "Process my data")
  no      = examples are placeholders, or no examples exist at all
  NOTE: if no examples exist at all, answer "no".

card_coherent:
  yes     = agent name, description, skill names, and tags all describe the same domain/purpose
  partial = mostly consistent but with minor mismatches
  no      = clear contradictions (e.g. name says "Finance" but skills are about image processing)

io_explained:
  yes     = description or skills explicitly mention what input is accepted or what output is produced
  partial = vaguely implied but not stated
  no      = no mention of inputs, outputs, formats, or what the agent returns
"""


def _build_user_message(card: AgentCard) -> str:
    """Compact but complete card representation for the prompt."""
    lines = [
        f"Agent name: {card.name}",
        f"Agent description: {card.description or '(none)'}",
        f"Number of skills: {len(card.skills)}",
        "",
        "Skills:",
    ]
    for skill in card.skills:
        lines += [
            f"  ID: {skill.id}",
            f"  Name: {skill.name}",
            f"  Description: {skill.description or '(none)'}",
            f"  Tags: {', '.join(skill.tags) if skill.tags else '(none)'}",
            f"  Examples: {'; '.join(skill.examples) if skill.examples else '(none)'}",
            "",
        ]
    if card.provider:
        lines.append(f"Provider: {card.provider.organization}")
    return "\n".join(lines)


def _coerce_answer(raw: Any) -> str:
    """Normalise model answer to 'yes', 'partial', or 'no'. Default: 'no'."""
    v = str(raw).strip().lower()
    if v in ("yes", "partial", "no"):
        return v
    # Tolerate common near-misses
    if v.startswith("yes"):
        return "yes"
    if v.startswith("part"):
        return "partial"
    return "no"


def analyze(card: AgentCard) -> DimensionResult:
    """
    Ask the model 5 categorical questions, then convert answers to points
    deterministically in Python.

    Returns 0-score DimensionResult with a warning if:
      - GEMINI_API_KEY is missing / placeholder
      - google-genai package is not installed
      - API call fails
      - Response cannot be parsed
    """
    checks: list[str]             = []
    failures: list[str]           = []
    suggestions: list[Suggestion] = []

    # ── Guard: API key ─────────────────────────────────────────────────────
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "your-api-key-here":
        failures.append(
            "GEMINI_API_KEY not configured — add your key to .env and "
            "re-run with --deep to enable AI quality analysis."
        )
        return DimensionResult(
            name="AI Quality",
            score=0.0,
            max_score=_TOTAL_MAX,
            checks=checks,
            failures=failures,
            suggestions=suggestions,
        )

    # ── Guard: google-genai package ────────────────────────────────────────
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        failures.append(
            "Package 'google-genai' is not installed. "
            "Run: pip install \"agentcard-disco[deep]\""
        )
        return DimensionResult(
            name="AI Quality",
            score=0.0,
            max_score=_TOTAL_MAX,
            checks=checks,
            failures=failures,
            suggestions=suggestions,
        )

    # ── Single API call (with retry + backoff) ────────────────────────────
    model = os.environ.get("AGENTCARD_DISCO_MODEL", _DEFAULT_MODEL)
    client = genai.Client(api_key=api_key)
    raw_text = ""
    last_exc: Exception | None = None

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model,
                contents=_build_user_message(card),
                config=types.GenerateContentConfig(
                    system_instruction=_SYSTEM_PROMPT,
                    temperature=0,          # determinism
                    max_output_tokens=400,  # answers are short
                    response_mime_type="application/json",  # guaranteed valid JSON
                ),
            )
            raw_text = response.text or ""
            break  # success — exit retry loop
        except Exception as exc:
            last_exc = exc
            err_str = str(exc)

            # Handle rate limits (429) specifically by respecting the retryDelay hint
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                # Extract suggested delay (e.g., '45s') if present in the error metadata
                match = re.search(r"retryDelay':\s*'(\d+)s'", err_str)
                wait_secs = int(match.group(1)) + 1 if match else 10
                
                if attempt < 2:
                    time.sleep(wait_secs)
                    continue

            if attempt < 2:
                time.sleep(2 ** attempt)  # 1s, 2s backoff
    else:
        err_msg = str(last_exc)
        if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
            failures.append("AI Quality analysis skipped: Gemini API quota exceeded (Rate Limit).")
        else:
            failures.append(f"AI API call failed: {last_exc}")

        return DimensionResult(
            name="AI Quality",
            score=0.0,
            max_score=_TOTAL_MAX,
            checks=checks,
            failures=failures,
            suggestions=suggestions,
        )

    # ── Parse ──────────────────────────────────────────────────────────────
    try:
        data: dict[str, Any] = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        failures.append(f"AI response could not be parsed: {exc}")
        return DimensionResult(
            name="AI Quality",
            score=0.0,
            max_score=_TOTAL_MAX,
            checks=checks,
            failures=failures,
            suggestions=suggestions,
        )

    # ── Score: Python converts answers → points ────────────────────────────
    total_score = 0.0

    for question_key, point_table in _POINTS.items():
        block  = data.get(question_key, {})
        answer = _coerce_answer(block.get("answer", "no"))
        reason = str(block.get("reason", "")).strip()
        pts    = point_table[answer]
        label  = _QUESTION_LABELS[question_key]

        total_score += pts

        if answer == "yes":
            checks.append(
                f"{label} — {reason}" if reason else label
            )
        elif answer == "partial":
            failures.append(
                f"{label} (partial) — {reason}" if reason else f"{label} (partial)"
            )
            # Partial = room to improve → suggestion
            suggestions.append(Suggestion(
                dimension="AI Quality",
                priority=2,
                message=f"Improve: {label.lower()}. {reason}".rstrip(".") + ".",
                field=_field_hint(question_key),
            ))
        else:  # no
            failures.append(
                f"{label} — {reason}" if reason else f"{label} — not met"
            )
            suggestions.append(Suggestion(
                dimension="AI Quality",
                priority=1,
                message=f"Fix: {label.lower()}. {reason}".rstrip(".") + ".",
                field=_field_hint(question_key),
            ))

    return DimensionResult(
        name="AI Quality",
        score=round(total_score, 1),
        max_score=_TOTAL_MAX,
        checks=checks,
        failures=failures,
        suggestions=suggestions,
    )


def _field_hint(question_key: str) -> str:
    """Map a question key to the most relevant AgentCard field path."""
    return {
        "description_specific": "description / skills[*].description",
        "skills_distinct":       "skills[*].description",
        "examples_realistic":    "skills[*].examples",
        "card_coherent":         "name / skills[*].tags",
        "io_explained":          "description / skills[*].description",
    }.get(question_key, "—")


# ── Remote deep scoring (via agentcard-disco API) ──────────────────────────

def analyze_via_api(card: AgentCard, api_key: str, api_base: str) -> DimensionResult:
    """
    Run Tier-2 AI Quality scoring via the hosted API instead of calling
    Gemini directly. Used when the user has configured an API key via
    `agentcard-disco auth <key>` but has no local GEMINI_API_KEY.

    Falls back to a 0-score result with a clear message on any failure.
    """
    import json as _json
    import urllib.request
    import urllib.error

    checks: list[str]             = []
    failures: list[str]           = []
    suggestions: list[Suggestion] = []

    card_dict = {
        "name": card.name,
        "description": card.description,
        "skills": [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "tags": s.tags,
                "examples": s.examples,
            }
            for s in card.skills
        ],
    }

    payload = _json.dumps({"card": card_dict, "deep": True}).encode()
    url = f"{api_base.rstrip('/')}/v1/score"

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = _json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        failures.append(f"API deep scoring failed ({e.code}): {body[:200]}")
        return DimensionResult(
            name="AI Quality",
            score=0.0,
            max_score=_TOTAL_MAX,
            checks=checks,
            failures=failures,
            suggestions=suggestions,
        )
    except Exception as exc:
        failures.append(f"API deep scoring failed: {exc}")
        return DimensionResult(
            name="AI Quality",
            score=0.0,
            max_score=_TOTAL_MAX,
            checks=checks,
            failures=failures,
            suggestions=suggestions,
        )

    # Extract the deep dimension result from the API response
    deep = data.get("deep", {})
    observations = deep.get("observations", {})
    bonus_points  = deep.get("bonus_points", {})
    bonus_total   = deep.get("bonus_total", 0.0)

    for key, answer in observations.items():
        label = key.replace("_", " ").capitalize()
        pts   = bonus_points.get(key, 0)
        if answer == "yes":
            checks.append(f"{label} ✓")
        elif answer == "partial":
            failures.append(f"{label} (partial)")
            suggestions.append(Suggestion(
                dimension="AI Quality",
                priority=2,
                message=f"Improve: {label.lower()}.",
                field="—",
            ))
        else:
            failures.append(f"{label} — not met")
            suggestions.append(Suggestion(
                dimension="AI Quality",
                priority=1,
                message=f"Fix: {label.lower()}.",
                field="—",
            ))

    return DimensionResult(
        name="AI Quality",
        score=round(float(bonus_total), 1),
        max_score=_TOTAL_MAX,
        checks=checks,
        failures=failures,
        suggestions=suggestions,
    )