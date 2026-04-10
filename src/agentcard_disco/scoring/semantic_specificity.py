"""
Analyzer 2 — Semantic Specificity (0–30 points)

Evaluates whether the text in an AgentCard is specific and meaningful,
not vague or generic. Uses zero ML dependencies — pure heuristic text analysis.

Checks:
  1. Filler-word ratio in descriptions          (0-10 pts)
  2. Inter-skill Jaccard similarity             (0-10 pts)  — penalises copy-paste skills
  3. Verb + noun density in descriptions        (0-10 pts)  — rewards action-oriented language
"""

from __future__ import annotations

import string
from collections import Counter
from itertools import combinations

from agentcard_disco.models import AgentCard
from agentcard_disco.scoring.result import DimensionResult, Suggestion

# ── Filler / vague word list ───────────────────────────────────────────────
# Words that carry almost no discriminating information about what an agent does.
_FILLER_WORDS: frozenset[str] = frozenset({
    # Generic verbs
    "do", "does", "doing", "done", "make", "makes", "making", "made",
    "help", "helps", "helping", "helped", "assist", "assists", "handle",
    "handles", "handling", "support", "supports", "supporting", "provide",
    "provides", "providing", "use", "uses", "using", "used", "get", "gets",
    "getting", "give", "gives", "giving", "allow", "allows", "enable",
    "enables", "work", "works", "working", "perform", "performs", "run",
    "runs", "running", "process", "processes", "processing", "manage",
    "manages", "managing", "execute", "executes", "executing",
    # Generic nouns
    "thing", "things", "stuff", "item", "items", "task", "tasks",
    "action", "actions", "result", "results", "output", "outputs",
    "input", "inputs", "data", "information", "content", "feature",
    "features", "functionality", "capability", "service", "services",
    "system", "systems", "tool", "tools", "function", "functions",
    # Generic adjectives / adverbs
    "various", "different", "many", "multiple", "some", "any", "all",
    "basic", "simple", "easy", "good", "great", "better", "best",
    "useful", "powerful", "advanced", "smart", "intelligent",
    "efficient", "effective", "robust", "flexible", "general",
    # Filler phrases encoded as words
    "etc", "etc.", "also", "just", "like", "really", "very", "quite",
})

# ── Action verbs that signal specificity ──────────────────────────────────
_ACTION_VERBS: frozenset[str] = frozenset({
    "analyze", "analyse", "compute", "calculate", "generate", "extract",
    "transform", "convert", "validate", "classify", "detect", "identify",
    "summarise", "summarize", "translate", "parse", "query", "retrieve",
    "filter", "aggregate", "merge", "split", "rank", "score", "predict",
    "recommend", "search", "index", "embed", "cluster", "annotate",
    "ingest", "export", "import", "monitor", "schedule", "notify",
    "compare", "benchmark", "optimise", "optimize", "simulate",
    "transcribe", "encode", "decode", "compress", "encrypt", "sign",
})

# ── Domain nouns that signal specificity ─────────────────────────────────
_DOMAIN_NOUNS: frozenset[str] = frozenset({
    "csv", "json", "parquet", "xml", "html", "markdown", "pdf",
    "dataset", "schema", "endpoint", "api", "webhook", "stream",
    "pipeline", "workflow", "report", "chart", "graph", "table",
    "metric", "anomaly", "outlier", "embedding", "vector", "token",
    "query", "sql", "database", "repository", "artifact", "model",
    "invoice", "order", "ticket", "event", "log", "trace", "alert",
    "sentiment", "entity", "relation", "knowledge", "taxonomy",
})

# ── Thresholds ─────────────────────────────────────────────────────────────
_FILLER_RATIO_GOOD = 0.08       # ≤ 8 % filler words → full points
_FILLER_RATIO_BAD = 0.25        # ≥ 25 % → zero points
_JACCARD_BAD = 0.5              # similarity ≥ 50 % between any two skills → penalty
_JACCARD_WARN = 0.30            # similarity ≥ 30 % → warning
_DENSITY_GOOD = 0.12            # action+domain tokens ≥ 12 % of total → full points
_DENSITY_OK = 0.05              # ≥ 5 % → partial


def _tokenize(text: str) -> list[str]:
    """Lowercase, strip punctuation, split into tokens."""
    text = text.lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    return [t for t in text.split() if len(t) > 1]


def _filler_ratio(tokens: list[str]) -> float:
    if not tokens:
        return 0.0
    filler_count = sum(1 for t in tokens if t in _FILLER_WORDS)
    return filler_count / len(tokens)


def _action_density(tokens: list[str]) -> float:
    if not tokens:
        return 0.0
    specific = sum(1 for t in tokens if t in _ACTION_VERBS or t in _DOMAIN_NOUNS)
    return specific / len(tokens)


def _jaccard(set_a: set[str], set_b: set[str]) -> float:
    if not set_a and not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union else 0.0


def analyze(card: AgentCard) -> DimensionResult:
    score = 0.0
    checks: list[str] = []
    failures: list[str] = []
    suggestions: list[Suggestion] = []

    # ── Collect all description text ──────────────────────────────────────
    all_desc_parts: list[str] = []
    if card.description:
        all_desc_parts.append(card.description)
    for skill in card.skills:
        if skill.description:
            all_desc_parts.append(skill.description)

    all_tokens = _tokenize(" ".join(all_desc_parts))

    # ── 1. Filler-word ratio (0-10 pts) ───────────────────────────────────
    filler = _filler_ratio(all_tokens)

    if not all_tokens:
        failures.append("No description text to analyse for filler words")
        # 0 pts
    elif filler <= _FILLER_RATIO_GOOD:
        score += 10.0
        checks.append(
            f"Filler-word ratio is low ({filler:.0%}) — language is specific and precise"
        )
    elif filler <= _FILLER_RATIO_BAD:
        # Linear interpolation between good and bad
        ratio = 1.0 - (filler - _FILLER_RATIO_GOOD) / (_FILLER_RATIO_BAD - _FILLER_RATIO_GOOD)
        pts = round(10.0 * ratio, 2)
        score += pts
        failures.append(
            f"Filler-word ratio is moderate ({filler:.0%}) — consider replacing vague words"
        )
        # Surface the top filler words so the dev can act on them
        token_counts = Counter(t for t in all_tokens if t in _FILLER_WORDS)
        top_fillers = [w for w, _ in token_counts.most_common(5)]
        suggestions.append(Suggestion(
            dimension="Semantic Specificity",
            priority=2,
            message=(
                f"Reduce generic language. Most frequent vague words: {', '.join(top_fillers)}. "
                "Replace with specific domain terms describing what the agent actually does."
            ),
            field="description / skills[*].description",
        ))
    else:
        failures.append(
            f"Filler-word ratio is high ({filler:.0%}) — descriptions are too generic"
        )
        token_counts = Counter(t for t in all_tokens if t in _FILLER_WORDS)
        top_fillers = [w for w, _ in token_counts.most_common(5)]
        suggestions.append(Suggestion(
            dimension="Semantic Specificity",
            priority=1,
            message=(
                f"Descriptions are dominated by vague language (top words: {', '.join(top_fillers)}). "
                "Rewrite to describe specific inputs, outputs, algorithms, or domain objects."
            ),
            field="description / skills[*].description",
        ))

    # ── 2. Inter-skill Jaccard similarity (0-10 pts) ──────────────────────
    skill_token_sets: list[tuple[str, set[str]]] = []
    for skill in card.skills:
        tokens = set(_tokenize(skill.description or ""))
        skill_token_sets.append((skill.id, tokens))

    if len(skill_token_sets) < 2:
        # Single skill: can't compare, award full points
        score += 10.0
        checks.append("Only one skill — no inter-skill similarity to penalise")
    else:
        max_similarity = 0.0
        worst_pair: tuple[str, str] = (skill_token_sets[0][0], skill_token_sets[1][0])

        for (id_a, set_a), (id_b, set_b) in combinations(skill_token_sets, 2):
            sim = _jaccard(set_a, set_b)
            if sim > max_similarity:
                max_similarity = sim
                worst_pair = (id_a, id_b)

        if max_similarity < _JACCARD_WARN:
            score += 10.0
            checks.append(
                f"Skills are semantically distinct (max Jaccard similarity: {max_similarity:.0%})"
            )
        elif max_similarity < _JACCARD_BAD:
            score += 5.0
            failures.append(
                f"Skills '{worst_pair[0]}' and '{worst_pair[1]}' have overlapping descriptions "
                f"({max_similarity:.0%} similar) — differentiate them more clearly"
            )
            suggestions.append(Suggestion(
                dimension="Semantic Specificity",
                priority=2,
                message=(
                    f"Skills '{worst_pair[0]}' and '{worst_pair[1]}' share too much vocabulary. "
                    "Each skill description should use distinct domain terms that highlight "
                    "what makes it unique from other skills."
                ),
                field=f"skills[{worst_pair[0]}].description / skills[{worst_pair[1]}].description",
            ))
        else:
            failures.append(
                f"Skills '{worst_pair[0]}' and '{worst_pair[1]}' descriptions are nearly "
                f"identical ({max_similarity:.0%} Jaccard similarity)"
            )
            suggestions.append(Suggestion(
                dimension="Semantic Specificity",
                priority=1,
                message=(
                    f"Skills '{worst_pair[0]}' and '{worst_pair[1]}' look like copy-paste. "
                    "LLM orchestrators will struggle to choose between them. "
                    "Rewrite each with unique, precise language describing its specific behaviour."
                ),
                field=f"skills[{worst_pair[0]}].description / skills[{worst_pair[1]}].description",
            ))

    # ── 3. Action-verb + domain-noun density (0-10 pts) ───────────────────
    density = _action_density(all_tokens)

    if not all_tokens:
        failures.append("No text to evaluate for action/domain density")
    elif density >= _DENSITY_GOOD:
        score += 10.0
        checks.append(
            f"Descriptions are rich in specific action verbs and domain nouns ({density:.0%} density)"
        )
    elif density >= _DENSITY_OK:
        ratio = (density - _DENSITY_OK) / (_DENSITY_GOOD - _DENSITY_OK)
        pts = round(10.0 * ratio, 2)
        score += pts
        failures.append(
            f"Action/domain term density is low ({density:.0%}) — add more precise vocabulary"
        )
        suggestions.append(Suggestion(
            dimension="Semantic Specificity",
            priority=2,
            message=(
                "Use more specific action verbs (e.g. 'extract', 'classify', 'aggregate') "
                "and domain nouns (e.g. 'CSV', 'JSON', 'anomaly', 'pipeline') in descriptions. "
                "These terms directly improve how orchestrators match tasks to skills."
            ),
            field="description / skills[*].description",
        ))
    else:
        failures.append(
            f"Very low action/domain density ({density:.0%}) — descriptions lack technical specificity"
        )
        suggestions.append(Suggestion(
            dimension="Semantic Specificity",
            priority=1,
            message=(
                "Descriptions are missing technical vocabulary. Use precise action verbs "
                "(e.g. 'parse', 'transform', 'query') and domain terms relevant to the "
                "agent's field. Avoid vague abstractions."
            ),
            field="description / skills[*].description",
        ))

    return DimensionResult(
        name="Semantic Specificity",
        score=round(score, 2),
        max_score=30.0,
        checks=checks,
        failures=failures,
        suggestions=suggestions,
    )
