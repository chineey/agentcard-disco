"""
Unit tests for ai_quality analyzer — all external calls are mocked.

Run with:  pytest tests/unit/test_ai_quality.py -v
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from agentcard_disco.models import AgentCard
from agentcard_disco.scoring import ai_quality


# ── Fixture helpers ────────────────────────────────────────────────────────

def _make_card(**overrides) -> AgentCard:
    base = {
        "name": "Test Agent",
        "url": "https://example.com/a2a",
        "version": "1.0.0",
        "capabilities": {"streaming": False, "pushNotifications": False},
        "description": "Analyses and extracts structured data from CSV and JSON datasets.",
        "skills": [
            {
                "id": "analyse",
                "name": "Analyse",
                "description": "Runs statistical analysis on tabular datasets.",
                "tags": ["analysis", "csv", "statistics"],
                "examples": ["Analyse this CSV file", "Compute summary statistics"],
            }
        ],
    }
    base.update(overrides)
    return AgentCard.model_validate(base)


def _good_response() -> dict:
    """A well-formed model response where every answer is 'yes'."""
    return {
        "description_specific": {"answer": "yes", "reason": "Uses domain terms like CSV and statistics."},
        "skills_distinct":       {"answer": "yes", "reason": "Only one skill, no overlap."},
        "examples_realistic":    {"answer": "yes", "reason": "Examples read like real user prompts."},
        "card_coherent":         {"answer": "yes", "reason": "Name, description, and tags all align."},
        "io_explained":          {"answer": "yes", "reason": "Inputs and outputs are described."},
    }


def _partial_response() -> dict:
    return {
        "description_specific": {"answer": "partial", "reason": "Mix of specific and vague language."},
        "skills_distinct":       {"answer": "yes",     "reason": "Only one skill."},
        "examples_realistic":    {"answer": "no",      "reason": "No examples exist."},
        "card_coherent":         {"answer": "yes",     "reason": "Consistent throughout."},
        "io_explained":          {"answer": "partial", "reason": "Vaguely implied but not stated."},
    }


def _mock_genai_response(payload: dict):
    """Build a mock google-genai response object."""
    mock_response = MagicMock()
    mock_response.text = json.dumps(payload)
    return mock_response


# ── Tests: missing API key ─────────────────────────────────────────────────

class TestMissingApiKey:
    def test_missing_key_returns_zero(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        card = _make_card()
        result = ai_quality.analyze(card)
        assert result.score == 0.0
        assert any("GEMINI_API_KEY" in f for f in result.failures)

    def test_placeholder_key_returns_zero(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "your-api-key-here")
        card = _make_card()
        result = ai_quality.analyze(card)
        assert result.score == 0.0


# ── Tests: missing package ─────────────────────────────────────────────────

class TestMissingPackage:
    def test_import_error_returns_zero(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
        with patch.dict("sys.modules", {"google": None, "google.genai": None, "google.genai.types": None}):
            card = _make_card()
            result = ai_quality.analyze(card)
        assert result.score == 0.0
        assert any("google-genai" in f for f in result.failures)


# ── Tests: successful API call ─────────────────────────────────────────────

class TestSuccessfulCall:
    def _run(self, monkeypatch, payload: dict) -> "ai_quality.DimensionResult":
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _mock_genai_response(payload)

        with patch("google.genai.Client", return_value=mock_client):
            with patch("google.genai.types"):
                card = _make_card()
                return ai_quality.analyze(card)

    def test_all_yes_gives_max_score(self, monkeypatch):
        result = self._run(monkeypatch, _good_response())
        assert result.score == 20.0
        assert result.max_score == 20.0

    def test_all_yes_no_failures(self, monkeypatch):
        result = self._run(monkeypatch, _good_response())
        assert result.failures == []

    def test_all_yes_checks_populated(self, monkeypatch):
        result = self._run(monkeypatch, _good_response())
        assert len(result.checks) == 5

    def test_partial_and_no_reduces_score(self, monkeypatch):
        result = self._run(monkeypatch, _partial_response())
        # partial: description_specific=3, io_explained=1 → 3+4+0+3+1 = 11
        assert result.score == 11.0

    def test_partial_produces_suggestions(self, monkeypatch):
        result = self._run(monkeypatch, _partial_response())
        assert len(result.suggestions) > 0

    def test_no_answer_produces_high_priority_suggestion(self, monkeypatch):
        result = self._run(monkeypatch, _partial_response())
        high = [s for s in result.suggestions if s.priority == 1]
        assert len(high) > 0

    def test_score_within_bounds(self, monkeypatch):
        for payload in (_good_response(), _partial_response()):
            result = self._run(monkeypatch, payload)
            assert 0 <= result.score <= result.max_score


# ── Tests: API failure ─────────────────────────────────────────────────────

class TestApiFailure:
    def test_api_exception_returns_zero(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("connection error")

        with patch("google.genai.Client", return_value=mock_client):
            with patch("google.genai.types"):
                result = ai_quality.analyze(_make_card())

        assert result.score == 0.0
        assert any("AI API call failed" in f for f in result.failures)

    def test_invalid_json_response_returns_zero(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
        mock_response = MagicMock()
        mock_response.text = "not valid json {"
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch("google.genai.Client", return_value=mock_client):
            with patch("google.genai.types"):
                result = ai_quality.analyze(_make_card())

        assert result.score == 0.0
        assert any("could not be parsed" in f for f in result.failures)

    def test_missing_keys_in_response_defaults_to_no(self, monkeypatch):
        """Partial/missing keys in the JSON should default to 'no', not crash."""
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _mock_genai_response({})

        with patch("google.genai.Client", return_value=mock_client):
            with patch("google.genai.types"):
                result = ai_quality.analyze(_make_card())

        assert result.score == 0.0  # all defaulted to 'no'


# ── Tests: answer coercion ─────────────────────────────────────────────────

class TestAnswerCoercion:
    def test_coerce_yes(self):
        assert ai_quality._coerce_answer("yes") == "yes"
        assert ai_quality._coerce_answer("YES") == "yes"
        assert ai_quality._coerce_answer("yes, definitely") == "yes"

    def test_coerce_partial(self):
        assert ai_quality._coerce_answer("partial") == "partial"
        assert ai_quality._coerce_answer("PARTIAL") == "partial"
        assert ai_quality._coerce_answer("partially") == "partial"

    def test_coerce_no(self):
        assert ai_quality._coerce_answer("no") == "no"
        assert ai_quality._coerce_answer("NO") == "no"
        assert ai_quality._coerce_answer("unknown_value") == "no"
