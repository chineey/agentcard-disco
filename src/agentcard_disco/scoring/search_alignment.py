"""
Analyzer 3 — Search Alignment (0–20 points)

Evaluates how well the agent's tags and descriptions align with the vocabulary
that developers and LLM orchestrators actually use when searching A2A registries.

Uses a curated dictionary of common A2A query terms grouped into intent clusters.
No ML — pure set intersection with normalised scoring.

Checks:
  1. Tag coverage against the query dictionary     (0-10 pts)
  2. Name + description keyword coverage           (0-6 pts)
  3. Input/output mode declaration alignment       (0-4 pts)
"""

from __future__ import annotations

import re
import string

from agentcard_disco.models import AgentCard
from agentcard_disco.scoring.result import DimensionResult, Suggestion

# ── Curated A2A search query dictionary ───────────────────────────────────
# Grouped by intent cluster. Flat set is used for scoring; clusters are kept
# for richer suggestions ("you match cluster X but not Y").

A2A_QUERY_CLUSTERS: dict[str, frozenset[str]] = {
    "data_processing": frozenset({
        "csv", "json", "parquet", "xml", "excel", "spreadsheet",
        "transform", "etl", "pipeline", "ingest", "extract", "load",
        "clean", "normalise", "normalize", "parse", "convert", "enrich",
    }),
    "analytics_intelligence": frozenset({
        "analysis", "analytics", "statistics", "anomaly", "outlier",
        "forecast", "predict", "trend", "correlation", "regression",
        "cluster", "segment", "classify", "score", "rank", "insight",
        "eda", "exploratory", "distribution", "metric", "kpi",
    }),
    "nlp_text": frozenset({
        "nlp", "text", "language", "summarise", "summarize", "translate",
        "sentiment", "entity", "extraction", "ner", "classification",
        "embedding", "vector", "search", "semantic", "chat", "dialogue",
        "question", "answering", "qa", "generation", "completion",
    }),
    "document_media": frozenset({
        "pdf", "document", "report", "invoice", "contract", "image",
        "ocr", "markdown", "html", "email", "form", "template",
        "chart", "graph", "visualise", "visualize", "diagram",
    }),
    "code_devtools": frozenset({
        "code", "git", "github", "repository", "pull", "review",
        "test", "lint", "debug", "deploy", "ci", "cd", "devops",
        "api", "sdk", "openapi", "swagger", "webhook", "endpoint",
    }),
    "data_retrieval": frozenset({
        "search", "query", "sql", "database", "retrieve", "fetch",
        "lookup", "index", "vector", "knowledge", "graph", "rag",
        "grounding", "context", "memory", "recall",
    }),
    "workflow_automation": frozenset({
        "workflow", "automation", "schedule", "trigger", "event",
        "notify", "alert", "monitor", "orchestrate", "coordinate",
        "task", "job", "queue", "async", "stream", "realtime",
    }),
    "enterprise_business": frozenset({
        "crm", "erp", "salesforce", "hubspot", "jira", "confluence",
        "slack", "email", "calendar", "hr", "finance", "accounting",
        "compliance", "audit", "security", "risk",
    }),
}

# Flat set of all query terms
_ALL_QUERY_TERMS: frozenset[str] = frozenset(
    term for cluster in A2A_QUERY_CLUSTERS.values() for term in cluster
)

# Common MIME types that registries and orchestrators filter by
_KNOWN_INPUT_MODES: frozenset[str] = frozenset({
    "text/plain", "application/json", "text/csv", "application/pdf",
    "text/html", "text/markdown", "image/png", "image/jpeg",
    "audio/mpeg", "application/xml",
})
_KNOWN_OUTPUT_MODES: frozenset[str] = frozenset({
    "text/plain", "application/json", "text/markdown", "text/html",
    "application/pdf", "image/png", "audio/mpeg", "application/xml",
})


def _tokenize(text: str) -> set[str]:
    text = text.lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    return {t for t in text.split() if len(t) > 1}


def analyze(card: AgentCard) -> DimensionResult:
    score = 0.0
    checks: list[str] = []
    failures: list[str] = []
    suggestions: list[Suggestion] = []

    # ── Gather all tags (normalised) ──────────────────────────────────────
    all_tags: set[str] = set()
    for skill in card.skills:
        for tag in skill.tags:
            all_tags.update(_tokenize(tag))

    # ── 1. Tag coverage (0-10 pts) ────────────────────────────────────────
    tag_hits = all_tags & _ALL_QUERY_TERMS
    matched_clusters: list[str] = []
    missed_clusters: list[str] = []

    for cluster_name, cluster_terms in A2A_QUERY_CLUSTERS.items():
        if all_tags & cluster_terms:
            matched_clusters.append(cluster_name)
        else:
            missed_clusters.append(cluster_name)

    # Score based on number of distinct query terms hit (capped at 10)
    hit_count = len(tag_hits)
    tag_pts = min(10.0, round(hit_count * (10.0 / 8), 2))  # 8 hits = full score
    score += tag_pts

    if hit_count >= 8:
        checks.append(
            f"Tags match {hit_count} registry query terms across "
            f"{len(matched_clusters)} intent cluster(s): {', '.join(matched_clusters)}"
        )
    elif hit_count > 0:
        checks.append(
            f"Tags match {hit_count} registry query term(s) — "
            f"clusters covered: {', '.join(matched_clusters) or 'none'}"
        )
        if missed_clusters:
            failures.append(
                f"No tags align with clusters: {', '.join(missed_clusters)}"
            )
            suggestions.append(Suggestion(
                dimension="Search Alignment",
                priority=2,
                message=(
                    f"Consider adding tags from these uncovered intent clusters: "
                    f"{', '.join(missed_clusters)}. "
                    "Even if the agent doesn't fully serve these clusters, "
                    "peripheral tags improve surface area in registry searches."
                ),
                field="skills[*].tags",
            ))
    else:
        failures.append("No tags match any known A2A registry search terms")
        suggestions.append(Suggestion(
            dimension="Search Alignment",
            priority=1,
            message=(
                "Tags are not aligned with A2A registry search vocabulary. "
                "Use terms from the common query clusters: "
                + ", ".join(f"'{c}'" for c in list(A2A_QUERY_CLUSTERS)[:4])
                + ". Match tags to the language developers use when searching for agents."
            ),
            field="skills[*].tags",
        ))

    # ── 2. Name + description keyword coverage (0-6 pts) ─────────────────
    text_tokens = _tokenize(
        " ".join(filter(None, [
            card.name,
            card.description,
            *(s.description for s in card.skills),
            *(s.name for s in card.skills),
        ]))
    )
    text_hits = text_tokens & _ALL_QUERY_TERMS
    text_hit_count = len(text_hits)

    text_pts = min(6.0, round(text_hit_count * (6.0 / 6), 2))  # 6 hits = full score
    score += text_pts

    if text_hit_count >= 6:
        checks.append(
            f"Name and descriptions contain {text_hit_count} registry-aligned keywords"
        )
    elif text_hit_count > 0:
        checks.append(
            f"Name/descriptions contain {text_hit_count} registry keyword(s)"
        )
        failures.append(
            "Description text could include more registry-aligned vocabulary"
        )
        suggestions.append(Suggestion(
            dimension="Search Alignment",
            priority=2,
            message=(
                "Weave more searchable keywords naturally into your descriptions. "
                f"Currently matching: {', '.join(sorted(text_hits)[:5])}. "
                "Add domain-specific terms that developers would use to find this agent."
            ),
            field="description / skills[*].description",
        ))
    else:
        failures.append(
            "Name and descriptions contain no registry-aligned keywords"
        )
        suggestions.append(Suggestion(
            dimension="Search Alignment",
            priority=1,
            message=(
                "Agent name and descriptions don't use vocabulary from A2A search queries. "
                "Rewrite to include terms from the relevant domain "
                "(e.g. 'analysis', 'extract', 'csv', 'pipeline', 'search')."
            ),
            field="name / description",
        ))

    # ── 3. I/O mode declaration (0-4 pts) ────────────────────────────────
    # Agents that declare specific MIME types get filtered-to in registry queries
    io_pts = 0.0

    # Aggregate all declared modes
    all_input_modes: set[str] = set(card.defaultInputModes)
    all_output_modes: set[str] = set(card.defaultOutputModes)
    for skill in card.skills:
        all_input_modes.update(skill.inputModes)
        all_output_modes.update(skill.outputModes)

    input_specific = all_input_modes - {"text", "text/plain"}
    output_specific = all_output_modes - {"text", "text/plain"}

    if input_specific:
        io_pts += 2.0
        checks.append(
            f"Specific input modes declared: {', '.join(sorted(input_specific))}"
        )
    else:
        failures.append(
            "Only generic input mode ('text/plain') declared — "
            "add specific MIME types to appear in filtered registry queries"
        )
        suggestions.append(Suggestion(
            dimension="Search Alignment",
            priority=2,
            message=(
                "Declare specific input MIME types (e.g. 'application/json', 'text/csv', "
                "'application/pdf') in 'defaultInputModes' or per-skill 'inputModes'. "
                "Registries use these for capability-based filtering."
            ),
            field="defaultInputModes / skills[*].inputModes",
        ))

    if output_specific:
        io_pts += 2.0
        checks.append(
            f"Specific output modes declared: {', '.join(sorted(output_specific))}"
        )
    else:
        failures.append(
            "Only generic output mode declared — specify richer output types"
        )
        suggestions.append(Suggestion(
            dimension="Search Alignment",
            priority=2,
            message=(
                "Declare specific output MIME types (e.g. 'application/json', 'text/markdown') "
                "so orchestrators can select this agent when they need a specific output format."
            ),
            field="defaultOutputModes / skills[*].outputModes",
        ))

    score += io_pts

    return DimensionResult(
        name="Search Alignment",
        score=round(score, 2),
        max_score=20.0,
        checks=checks,
        failures=failures,
        suggestions=suggestions,
    )
