"""
Analyzer 1 — Metadata Richness (0–30 points)

Evaluates the presence and quality of descriptive metadata fields:
  - Agent-level description length and substance
  - Per-skill description lengths
  - Tag population (agent + per-skill)
  - Example utterances per skill
  - Optional but high-value fields: provider, documentationUrl, iconUrl
"""

from __future__ import annotations

from agentcard_disco.models import AgentCard
from agentcard_disco.scoring.result import DimensionResult, Suggestion

# ── Point allocation ───────────────────────────────────────────────────────
# Total: 30

_AGENT_DESC_MAX = 8          # agent-level description
_SKILL_DESC_MAX = 8          # skill descriptions (pooled across all skills)
_TAGS_MAX = 6                # tag population
_EXAMPLES_MAX = 5            # example utterances
_OPTIONAL_FIELDS_MAX = 3     # provider, documentationUrl, iconUrl

# Thresholds
_AGENT_DESC_GOOD = 100       # chars for full points
_AGENT_DESC_OK = 40          # chars for partial credit
_SKILL_DESC_GOOD = 60        # chars per skill for full credit
_SKILL_DESC_OK = 20          # chars per skill for partial credit
_TAGS_PER_SKILL_TARGET = 3   # desired tags per skill


def analyze(card: AgentCard) -> DimensionResult:
    score = 0.0
    checks: list[str] = []
    failures: list[str] = []
    suggestions: list[Suggestion] = []

    # ── 1. Agent-level description (0-8 pts) ──────────────────────────────
    desc = (card.description or "").strip()
    desc_len = len(desc)

    if desc_len >= _AGENT_DESC_GOOD:
        score += _AGENT_DESC_MAX
        checks.append(
            f"Agent description is thorough ({desc_len} chars)"
        )
    elif desc_len >= _AGENT_DESC_OK:
        pts = round(_AGENT_DESC_MAX * 0.5, 1)
        score += pts
        failures.append(
            f"Agent description is brief ({desc_len} chars) — aim for {_AGENT_DESC_GOOD}+"
        )
        suggestions.append(Suggestion(
            dimension="Metadata Richness",
            priority=1,
            message=(
                f"Expand the agent description to at least {_AGENT_DESC_GOOD} characters. "
                "Describe the agent's purpose, target use case, and what kinds of pipelines it fits into."
            ),
            field="description",
        ))
    elif desc_len > 0:
        pts = round(_AGENT_DESC_MAX * 0.2, 1)
        score += pts
        failures.append(f"Agent description is very short ({desc_len} chars)")
        suggestions.append(Suggestion(
            dimension="Metadata Richness",
            priority=1,
            message=(
                "The agent description is too short to be useful. Aim for at least "
                f"{_AGENT_DESC_GOOD} characters describing purpose, domain, and capabilities."
            ),
            field="description",
        ))
    else:
        failures.append("Agent description is missing entirely")
        suggestions.append(Suggestion(
            dimension="Metadata Richness",
            priority=1,
            message=(
                "Add a top-level 'description' field. This is the first thing LLM orchestrators "
                "and registry search engines use to determine agent relevance."
            ),
            field="description",
        ))

    # ── 2. Skill descriptions (0-8 pts) ───────────────────────────────────
    num_skills = len(card.skills)
    skill_desc_scores: list[float] = []

    for skill in card.skills:
        sdesc = (skill.description or "").strip()
        slen = len(sdesc)
        if slen >= _SKILL_DESC_GOOD:
            skill_desc_scores.append(1.0)
        elif slen >= _SKILL_DESC_OK:
            skill_desc_scores.append(0.5)
            failures.append(
                f"Skill '{skill.id}' description is brief ({slen} chars)"
            )
            suggestions.append(Suggestion(
                dimension="Metadata Richness",
                priority=2,
                message=(
                    f"Expand the description for skill '{skill.id}'. "
                    f"Aim for {_SKILL_DESC_GOOD}+ chars explaining inputs, outputs, and use case."
                ),
                field=f"skills[{skill.id}].description",
            ))
        else:
            skill_desc_scores.append(0.0)
            failures.append(
                f"Skill '{skill.id}' has a very short or missing description ({slen} chars)"
            )
            suggestions.append(Suggestion(
                dimension="Metadata Richness",
                priority=1,
                message=(
                    f"Skill '{skill.id}' needs a proper description. "
                    "Explain what the skill does, what inputs it accepts, and what it returns."
                ),
                field=f"skills[{skill.id}].description",
            ))

    if skill_desc_scores:
        avg = sum(skill_desc_scores) / len(skill_desc_scores)
        pts = round(avg * _SKILL_DESC_MAX, 2)
        score += pts
        good_count = sum(1 for s in skill_desc_scores if s == 1.0)
        if good_count == num_skills:
            checks.append(f"All {num_skills} skill descriptions are thorough")
        else:
            checks.append(f"{good_count}/{num_skills} skill descriptions meet the length target")

    # ── 3. Tags (0-6 pts) ─────────────────────────────────────────────────
    skills_with_tags = [s for s in card.skills if len(s.tags) >= _TAGS_PER_SKILL_TARGET]
    skills_with_some_tags = [s for s in card.skills if 0 < len(s.tags) < _TAGS_PER_SKILL_TARGET]
    skills_no_tags = [s for s in card.skills if not s.tags]

    if len(skills_with_tags) == num_skills:
        score += _TAGS_MAX
        checks.append(
            f"All {num_skills} skills have {_TAGS_PER_SKILL_TARGET}+ tags each"
        )
    elif skills_with_some_tags or skills_with_tags:
        ratio = (len(skills_with_tags) + 0.5 * len(skills_with_some_tags)) / num_skills
        pts = round(ratio * _TAGS_MAX, 2)
        score += pts
        checks.append(f"{len(skills_with_tags)}/{num_skills} skills fully tagged")
        if skills_no_tags:
            failures.append(
                f"{len(skills_no_tags)} skill(s) have no tags: "
                + ", ".join(f"'{s.id}'" for s in skills_no_tags)
            )
            suggestions.append(Suggestion(
                dimension="Metadata Richness",
                priority=2,
                message=(
                    f"Add at least {_TAGS_PER_SKILL_TARGET} tags to each skill. "
                    "Tags are the primary search index in A2A registries."
                ),
                field="skills[*].tags",
            ))
    else:
        failures.append("No skills have any tags — registry search will miss this agent")
        suggestions.append(Suggestion(
            dimension="Metadata Richness",
            priority=1,
            message=(
                f"Add at least {_TAGS_PER_SKILL_TARGET} descriptive tags to every skill. "
                "Use domain terms, action verbs, and technology names relevant to the skill."
            ),
            field="skills[*].tags",
        ))

    # ── 4. Examples (0-5 pts) ─────────────────────────────────────────────
    skills_with_examples = [s for s in card.skills if s.examples]
    ex_ratio = len(skills_with_examples) / num_skills if num_skills else 0

    if ex_ratio == 1.0:
        score += _EXAMPLES_MAX
        avg_ex = sum(len(s.examples) for s in card.skills) / num_skills
        checks.append(
            f"All skills have examples (avg {avg_ex:.1f} per skill)"
        )
    elif ex_ratio > 0:
        pts = round(ex_ratio * _EXAMPLES_MAX, 2)
        score += pts
        missing = [s.id for s in card.skills if not s.examples]
        failures.append(
            f"Skills missing examples: {', '.join(missing)}"
        )
        suggestions.append(Suggestion(
            dimension="Metadata Richness",
            priority=2,
            message=(
                "Add 2-3 example utterances per skill. Examples dramatically improve "
                "LLM orchestrator skill selection accuracy."
            ),
            field="skills[*].examples",
        ))
    else:
        failures.append("No skills have any example utterances")
        suggestions.append(Suggestion(
            dimension="Metadata Richness",
            priority=1,
            message=(
                "Add 'examples' to every skill. These are real user prompts that would invoke "
                "the skill — they act as semantic anchors for LLM-based orchestrators."
            ),
            field="skills[*].examples",
        ))

    # ── 5. Optional enrichment fields (0-3 pts) ───────────────────────────
    optional_pts = 0.0
    if card.provider:
        optional_pts += 1.0
        checks.append("Provider information present")
    else:
        failures.append("No provider information")
        suggestions.append(Suggestion(
            dimension="Metadata Richness",
            priority=3,
            message="Add a 'provider' block with organisation name and URL. Builds trust in registries.",
            field="provider",
        ))

    if card.documentationUrl:
        optional_pts += 1.0
        checks.append("Documentation URL present")
    else:
        failures.append("No documentationUrl")
        suggestions.append(Suggestion(
            dimension="Metadata Richness",
            priority=3,
            message="Add a 'documentationUrl' pointing to usage docs. Reduces integration friction.",
            field="documentationUrl",
        ))

    if card.iconUrl:
        optional_pts += 1.0
        checks.append("Icon URL present")

    score += optional_pts

    return DimensionResult(
        name="Metadata Richness",
        score=round(score, 2),
        max_score=float(
            _AGENT_DESC_MAX + _SKILL_DESC_MAX + _TAGS_MAX + _EXAMPLES_MAX + _OPTIONAL_FIELDS_MAX
        ),
        checks=checks,
        failures=failures,
        suggestions=suggestions,
    )
