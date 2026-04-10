"""
Non-terminal reporters: JSON and Markdown.

JSON  — machine-readable output for CI/CD pipelines, badge generators,
        and downstream tooling.
Markdown — human-readable report suitable for GitHub PR comments,
           wiki pages, and README sections.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from agentcard_disco.scoring.result import ScoreReport


# ── JSON ───────────────────────────────────────────────────────────────────

def to_json(report: ScoreReport, *, indent: int = 2) -> str:
    """
    Serialise a ScoreReport to a JSON string.

    The schema is stable and suitable for CI/CD consumption:
      - Top-level 'pass' key for simple threshold checks
      - Per-dimension breakdown with score, max, percentage, grade
      - All suggestions with priority, field, and message
    """
    data = {
        "meta": {
            "tool": "agentcard-disco",
            "version": "0.1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "card": {
            "name": report.card_name,
            "source": report.source,
        },
        "overall": {
            "score": report.total_score,
            "max": report.max_total,
            "percentage": report.percentage,
            "grade": report.grade.value,
            "pass": report.percentage >= 70,  # B or above = passing
            "ai_enhanced": report.ai_enhanced,
        },
        "dimensions": [
            {
                "name": d.name,
                "score": d.score,
                "max": d.max_score,
                "percentage": d.percentage,
                "grade": d.grade.value,
                "checks": d.checks,
                "failures": d.failures,
            }
            for d in report.dimensions
        ],
        "suggestions": [
            {
                "priority": s.priority,
                "dimension": s.dimension,
                "field": s.field,
                "message": s.message,
            }
            for s in report.all_suggestions
        ],
    }
    return json.dumps(data, indent=indent, ensure_ascii=False)


def write_json(report: ScoreReport, path: str, *, indent: int = 2) -> None:
    """Write JSON report to a file."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(to_json(report, indent=indent))


# ── Markdown ───────────────────────────────────────────────────────────────

_GRADE_BADGE: dict[str, str] = {
    "A": "brightgreen",
    "B": "green",
    "C": "yellow",
    "D": "orange",
    "F": "red",
}

_PRIORITY_EMOJI = {1: "🔴", 2: "🟡", 3: "🔵"}


def to_markdown(report: ScoreReport) -> str:
    """
    Render a ScoreReport as a Markdown string.

    Suitable for:
      - Pasting into GitHub PR comments
      - Saving as a .md file alongside an Agent Card
      - Including in documentation sites
    """
    grade = report.grade
    badge_color = _GRADE_BADGE[grade.value]
    badge_url = (
        f"https://img.shields.io/badge/disco--score-"
        f"{report.percentage:.0f}%25%20{grade.value}-{badge_color}"
    )

    lines: list[str] = []

    # Header
    lines += [
        "# Agent Card Discoverability Report",
        "",
        f"![disco score]({badge_url})",
        "",
        f"**Card:** `{report.card_name}`  ",
        f"**Source:** `{report.source}`  ",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "---",
        "",
    ]

    # Overall score
    bar_filled = round(report.percentage / 100 * 20)
    bar = "█" * bar_filled + "░" * (20 - bar_filled)
    lines += [
        "## Overall Score",
        "",
        "```",
        f"{bar}  {report.total_score:.1f} / {report.max_total:.0f}  ({report.percentage:.0f}%)  Grade: {grade.value}",
        "```",
        "",
    ]

    # Dimension table
    lines += [
        "## Dimension Breakdown",
        "",
        "| Dimension | Score | % | Grade |",
        "|-----------|------:|--:|:-----:|",
    ]
    for d in report.dimensions:
        pct_bar = "█" * round(d.percentage / 10) + "░" * (10 - round(d.percentage / 10))
        lines.append(
            f"| {d.name} | {d.score:.1f} / {d.max_score:.0f} | {pct_bar} {d.percentage:.0f}% | **{d.grade.value}** |"
        )
    lines.append("")

    # Per-dimension detail
    lines += ["## Detail", ""]
    for d in report.dimensions:
        lines += [f"### {d.name}  `{d.score:.1f}/{d.max_score:.0f} pts`", ""]
        for c in d.checks:
            lines.append(f"- ✅ {c}")
        for f in d.failures:
            lines.append(f"- ❌ {f}")
        lines.append("")

    # Suggestions
    suggestions = report.all_suggestions
    if suggestions:
        lines += [
            "## Improvement Suggestions",
            "",
            "| Priority | Dimension | Field | Action |",
            "|:--------:|-----------|-------|--------|",
        ]
        for s in suggestions:
            emoji = _PRIORITY_EMOJI[s.priority]
            field = f"`{s.field}`" if s.field else "—"
            lines.append(
                f"| {emoji} | {s.dimension} | {field} | {s.message} |"
            )
        lines.append("")

    # Footer
    high = sum(1 for s in suggestions if s.priority == 1)
    if high:
        lines += [
            "---",
            "",
            f"> ⚠️ **{high} high-priority issue(s)** must be addressed before publishing "
            "this card to an A2A registry.",
            "",
        ]
    elif grade.value in ("A", "B"):
        lines += [
            "---",
            "",
            "> ✅ This card is ready to publish to an A2A registry.",
            "",
        ]

    lines += [
        "---",
        "*Generated by [agentcard-disco](https://github.com/chinemeze/agentcard-disco)*",
    ]

    return "\n".join(lines)


def write_markdown(report: ScoreReport, path: str) -> None:
    """Write Markdown report to a file."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(to_markdown(report))
