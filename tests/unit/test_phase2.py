"""
Unit tests for Phase 2: scoring engine + all 4 analyzers.

Uses stdlib-only (json, pathlib) to build AgentCard fixtures without
needing pydantic installed in CI — model construction is tested via
pure dict-based fixture helpers that the scoring functions accept
after being converted.

NOTE: These tests import from agentcard_disco and require:
  pip install -e . (or the deps available in the environment)

Run with:  pytest tests/unit/test_phase2.py -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentcard_disco.models import AgentCard
from agentcard_disco.scoring import completeness, metadata_richness, search_alignment, semantic_specificity
from agentcard_disco.scoring.engine import score
from agentcard_disco.scoring.result import Grade

FIXTURES = Path(__file__).parent.parent / "fixtures"


# ── Fixture helpers ────────────────────────────────────────────────────────

def _make_card(**overrides) -> AgentCard:
    """Build a base valid AgentCard, merging in any overrides."""
    base = {
        "name": "Test Agent",
        "url": "https://example.com/a2a",
        "version": "1.0.0",
        "capabilities": {"streaming": False, "pushNotifications": False},
        "description": "A test agent that does test things for testing purposes.",
        "skills": [
            {
                "id": "skill_a",
                "name": "Skill A",
                "description": "Analyses and extracts data from CSV files using statistical methods.",
                "tags": ["analysis", "csv", "statistics"],
                "examples": ["analyse this CSV", "extract data from file"],
                "inputModes": ["text/csv"],
                "outputModes": ["application/json"],
            }
        ],
    }
    base.update(overrides)
    return AgentCard.model_validate(base)


def _load_fixture(name: str) -> AgentCard:
    return AgentCard.model_validate(json.loads((FIXTURES / name).read_text()))


# ── Grade ──────────────────────────────────────────────────────────────────

class TestGrade:
    def test_grade_boundaries(self):
        assert Grade.from_score(100) == Grade.A
        assert Grade.from_score(85) == Grade.A
        assert Grade.from_score(84) == Grade.B
        assert Grade.from_score(70) == Grade.B
        assert Grade.from_score(69) == Grade.C
        assert Grade.from_score(50) == Grade.C
        assert Grade.from_score(49) == Grade.D
        assert Grade.from_score(30) == Grade.D
        assert Grade.from_score(29) == Grade.F
        assert Grade.from_score(0) == Grade.F


# ── Metadata Richness ─────────────────────────────────────────────────────

class TestMetadataRichness:
    def test_good_card_scores_high(self):
        card = _load_fixture("good_card.json")
        result = metadata_richness.analyze(card)
        assert result.score >= 24  # 80%+ of 30
        assert result.max_score == 30

    def test_minimal_card_scores_low(self):
        card = _load_fixture("minimal_card.json")
        result = metadata_richness.analyze(card)
        assert result.score <= 10  # ≤ 33% for a bare card

    def test_missing_description_penalised(self):
        card = _make_card(description=None)
        result = metadata_richness.analyze(card)
        # Should have a suggestion about description
        desc_suggestions = [s for s in result.suggestions if s.field == "description"]
        assert len(desc_suggestions) > 0

    def test_no_tags_penalised(self):
        card = _make_card(skills=[{
            "id": "s1", "name": "S1",
            "description": "Does something specific",
            "tags": [], "examples": [],
        }])
        result = metadata_richness.analyze(card)
        tag_failures = [f for f in result.failures if "tag" in f.lower()]
        assert len(tag_failures) > 0

    def test_provider_gives_points(self):
        card_without = _make_card()
        card_with = _make_card(provider={"organization": "Acme", "url": "https://acme.io"})
        assert metadata_richness.analyze(card_with).score > metadata_richness.analyze(card_without).score

    def test_score_within_bounds(self):
        for fixture in ("good_card.json", "minimal_card.json"):
            card = _load_fixture(fixture)
            result = metadata_richness.analyze(card)
            assert 0 <= result.score <= result.max_score


# ── Semantic Specificity ───────────────────────────────────────────────────

class TestSemanticSpecificity:
    def test_good_card_scores_high(self):
        card = _load_fixture("good_card.json")
        result = semantic_specificity.analyze(card)
        assert result.score >= 18  # ≥60% for a rich card

    def test_filler_words_penalised(self):
        card = _make_card(
            description="This agent does stuff and helps with various things in a simple and easy way.",
            skills=[{
                "id": "s1", "name": "Do thing",
                "description": "Does the thing and helps make it work better with various features.",
                "tags": ["general"], "examples": [],
            }]
        )
        result = semantic_specificity.analyze(card)
        filler_failures = [f for f in result.failures if "filler" in f.lower()]
        assert len(filler_failures) > 0

    def test_copy_paste_skills_penalised(self):
        duplicate_desc = "Helps with general data processing tasks."
        card = _make_card(skills=[
            {"id": "s1", "name": "S1", "description": duplicate_desc, "tags": ["data"]},
            {"id": "s2", "name": "S2", "description": duplicate_desc, "tags": ["data"]},
        ])
        result = semantic_specificity.analyze(card)
        similarity_failures = [f for f in result.failures if "similar" in f.lower() or "identical" in f.lower()]
        assert len(similarity_failures) > 0

    def test_single_skill_no_jaccard_penalty(self):
        card = _make_card()
        result = semantic_specificity.analyze(card)
        single_checks = [c for c in result.checks if "one skill" in c.lower()]
        assert len(single_checks) > 0

    def test_score_within_bounds(self):
        for fixture in ("good_card.json", "minimal_card.json"):
            card = _load_fixture(fixture)
            result = semantic_specificity.analyze(card)
            assert 0 <= result.score <= result.max_score


# ── Search Alignment ───────────────────────────────────────────────────────

class TestSearchAlignment:
    def test_good_card_scores_high(self):
        card = _load_fixture("good_card.json")
        result = search_alignment.analyze(card)
        assert result.score >= 14  # ≥70% of 20

    def test_no_tags_scores_low(self):
        card = _make_card(skills=[{
            "id": "s1", "name": "S1",
            "description": "Does things",
            "tags": [], "examples": [],
        }])
        result = search_alignment.analyze(card)
        assert result.score < 10

    def test_specific_io_modes_rewarded(self):
        card_generic = _make_card()
        card_specific = _make_card(
            defaultInputModes=["text/csv", "application/json"],
            defaultOutputModes=["application/json", "text/markdown"],
        )
        assert search_alignment.analyze(card_specific).score >= search_alignment.analyze(card_generic).score

    def test_score_within_bounds(self):
        for fixture in ("good_card.json", "minimal_card.json"):
            card = _load_fixture(fixture)
            result = search_alignment.analyze(card)
            assert 0 <= result.score <= result.max_score


# ── Completeness ───────────────────────────────────────────────────────────

class TestCompleteness:
    def test_good_card_scores_high(self):
        card = _load_fixture("good_card.json")
        result = completeness.analyze(card)
        assert result.score >= 14  # ≥70% of 20

    def test_non_semver_penalised(self):
        card = _make_card(version="1")
        result = completeness.analyze(card)
        semver_failures = [f for f in result.failures if "semver" in f.lower() or "SemVer" in f]
        assert len(semver_failures) > 0

    def test_semver_rewarded(self):
        card_bad = _make_card(version="1")
        card_good = _make_card(version="1.0.0")
        assert completeness.analyze(card_good).score > completeness.analyze(card_bad).score

    def test_streaming_rewarded(self):
        card_no_stream = _make_card(capabilities={"streaming": False, "pushNotifications": False})
        card_stream = _make_card(capabilities={"streaming": True, "pushNotifications": False})
        assert completeness.analyze(card_stream).score > completeness.analyze(card_no_stream).score

    def test_no_security_penalised(self):
        card = _make_card()
        result = completeness.analyze(card)
        security_failures = [f for f in result.failures if "security" in f.lower() or "auth" in f.lower()]
        assert len(security_failures) > 0

    def test_score_within_bounds(self):
        for fixture in ("good_card.json", "minimal_card.json"):
            card = _load_fixture(fixture)
            result = completeness.analyze(card)
            assert 0 <= result.score <= result.max_score


# ── Engine integration ─────────────────────────────────────────────────────

class TestScoringEngine:
    def test_good_card_grade_a_or_b(self):
        card = _load_fixture("good_card.json")
        report = score(card, source="good_card.json")
        assert report.grade in (Grade.A, Grade.B)
        assert report.total_score >= 70

    def test_minimal_card_grade_d_or_f(self):
        card = _load_fixture("minimal_card.json")
        report = score(card, source="minimal_card.json")
        assert report.grade in (Grade.C, Grade.D, Grade.F)  # not A or B
        assert report.total_score < 70

    def test_report_has_all_dimensions(self):
        card = _load_fixture("good_card.json")
        report = score(card, source="good_card.json")
        names = {d.name for d in report.dimensions}
        assert "Metadata Richness" in names
        assert "Semantic Specificity" in names
        assert "Search Alignment" in names
        assert "Completeness" in names

    def test_total_score_within_bounds(self):
        for fixture in ("good_card.json", "minimal_card.json"):
            card = _load_fixture(fixture)
            report = score(card, source=fixture)
            assert 0 <= report.total_score <= report.max_total

    def test_all_suggestions_sorted_by_priority(self):
        card = _load_fixture("minimal_card.json")
        report = score(card, source="minimal_card.json")
        suggestions = report.all_suggestions
        priorities = [s.priority for s in suggestions]
        assert priorities == sorted(priorities)

    def test_source_preserved_in_report(self):
        card = _load_fixture("good_card.json")
        report = score(card, source="/custom/path/card.json")
        assert report.source == "/custom/path/card.json"
