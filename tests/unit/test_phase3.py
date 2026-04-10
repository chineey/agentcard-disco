"""
Unit tests for Phase 3: CLI commands + reporters.

Run with:  pytest tests/unit/test_phase3.py -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from agentcard_disco.cli.main import cli
from agentcard_disco.models import AgentCard
from agentcard_disco.reporting.exporters import to_json, to_markdown
from agentcard_disco.scoring.engine import score

FIXTURES = Path(__file__).parent.parent / "fixtures"
GOOD_CARD = str(FIXTURES / "good_card.json")
MINIMAL_CARD = str(FIXTURES / "minimal_card.json")


# ── Exporter: JSON ─────────────────────────────────────────────────────────

class TestJsonExporter:
    def _report(self, fixture: str):
        card = AgentCard.model_validate(json.loads(Path(FIXTURES / fixture).read_text()))
        return score(card, source=fixture)

    def test_json_is_valid(self):
        report = self._report("good_card.json")
        output = to_json(report)
        data = json.loads(output)
        assert "overall" in data
        assert "dimensions" in data
        assert "suggestions" in data
        assert "meta" in data

    def test_json_pass_flag_good_card(self):
        report = self._report("good_card.json")
        data = json.loads(to_json(report))
        assert data["overall"]["pass"] is True

    def test_json_pass_flag_minimal_card(self):
        report = self._report("minimal_card.json")
        data = json.loads(to_json(report))
        assert data["overall"]["pass"] is False

    def test_json_has_all_dimensions(self):
        report = self._report("good_card.json")
        data = json.loads(to_json(report))
        names = {d["name"] for d in data["dimensions"]}
        assert "Metadata Richness" in names
        assert "Completeness" in names

    def test_json_suggestions_sorted_by_priority(self):
        report = self._report("minimal_card.json")
        data = json.loads(to_json(report))
        priorities = [s["priority"] for s in data["suggestions"]]
        assert priorities == sorted(priorities)

    def test_write_json_to_file(self, tmp_path):
        from agentcard_disco.reporting.exporters import write_json
        report = self._report("good_card.json")
        out = tmp_path / "report.json"
        write_json(report, str(out))
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["card"]["name"] == "DataPulse Analytics Agent"


# ── Exporter: Markdown ─────────────────────────────────────────────────────

class TestMarkdownExporter:
    def _report(self, fixture: str):
        card = AgentCard.model_validate(json.loads(Path(FIXTURES / fixture).read_text()))
        return score(card, source=fixture)

    def test_markdown_contains_card_name(self):
        report = self._report("good_card.json")
        md = to_markdown(report)
        assert "DataPulse Analytics Agent" in md

    def test_markdown_contains_grade(self):
        report = self._report("good_card.json")
        md = to_markdown(report)
        grade = report.grade.value
        assert grade in md

    def test_markdown_contains_dimension_table(self):
        report = self._report("good_card.json")
        md = to_markdown(report)
        assert "Metadata Richness" in md
        assert "Semantic Specificity" in md
        assert "Search Alignment" in md
        assert "Completeness" in md

    def test_markdown_contains_suggestions(self):
        report = self._report("minimal_card.json")
        md = to_markdown(report)
        assert "Improvement Suggestions" in md

    def test_markdown_minimal_has_warning(self):
        report = self._report("minimal_card.json")
        md = to_markdown(report)
        assert "high-priority" in md.lower() or "⚠️" in md

    def test_write_markdown_to_file(self, tmp_path):
        from agentcard_disco.reporting.exporters import write_markdown
        report = self._report("good_card.json")
        out = tmp_path / "report.md"
        write_markdown(report, str(out))
        assert out.exists()
        assert "# Agent Card Discoverability Report" in out.read_text(encoding="utf-8")


# ── CLI: score command ─────────────────────────────────────────────────────

class TestScoreCommand:
    def setup_method(self):
        self.runner = CliRunner()

    def test_score_good_card_exits_zero(self):
        result = self.runner.invoke(cli, ["score", GOOD_CARD])
        assert result.exit_code == 0

    def test_score_minimal_card_exits_zero(self):
        result = self.runner.invoke(cli, ["score", MINIMAL_CARD])
        assert result.exit_code == 0

    def test_score_missing_file_exits_one(self):
        result = self.runner.invoke(cli, ["score", "/no/such/file.json"])
        assert result.exit_code == 1

    def test_score_json_format(self):
        result = self.runner.invoke(cli, ["score", GOOD_CARD, "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "overall" in data

    def test_score_markdown_format(self):
        result = self.runner.invoke(cli, ["score", GOOD_CARD, "--format", "markdown"])
        assert result.exit_code == 0
        assert "# Agent Card Discoverability Report" in result.output

    def test_score_fail_under_passes(self):
        result = self.runner.invoke(cli, ["score", GOOD_CARD, "--fail-under", "10"])
        assert result.exit_code == 0

    def test_score_fail_under_fails(self):
        result = self.runner.invoke(cli, ["score", MINIMAL_CARD, "--fail-under", "99"])
        assert result.exit_code == 1

    def test_score_no_suggestions_flag(self):
        result = self.runner.invoke(cli, ["score", GOOD_CARD, "--no-suggestions"])
        assert result.exit_code == 0
        assert "Improvement Suggestions" not in result.output

    def test_score_json_output_to_file(self, tmp_path):
        out = tmp_path / "report.json"
        result = self.runner.invoke(
            cli, ["score", GOOD_CARD, "--format", "json", "--output", str(out)]
        )
        assert result.exit_code == 0
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["card"]["name"] == "DataPulse Analytics Agent"


# ── CLI: suggest command ───────────────────────────────────────────────────

class TestSuggestCommand:
    def setup_method(self):
        self.runner = CliRunner()

    def test_suggest_exits_zero(self):
        result = self.runner.invoke(cli, ["suggest", MINIMAL_CARD])
        assert result.exit_code == 0

    def test_suggest_high_priority_only(self):
        result = self.runner.invoke(cli, ["suggest", MINIMAL_CARD, "--priority", "high"])
        assert result.exit_code == 0
        assert "HIGH" in result.output

    def test_suggest_json_format(self):
        result = self.runner.invoke(cli, ["suggest", MINIMAL_CARD, "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        if data:
            assert "priority" in data[0]
            assert "message" in data[0]

    def test_suggest_limit(self):
        result = self.runner.invoke(cli, ["suggest", MINIMAL_CARD, "--limit", "2"])
        assert result.exit_code == 0
        # 2 suggestions → at most 2 "●" markers in output
        assert result.output.count("●") <= 2


# ── CLI: compare command ───────────────────────────────────────────────────

class TestCompareCommand:
    def setup_method(self):
        self.runner = CliRunner()

    def test_compare_two_cards_exits_zero(self):
        result = self.runner.invoke(cli, ["compare", GOOD_CARD, MINIMAL_CARD])
        assert result.exit_code == 0

    def test_compare_shows_winner(self):
        result = self.runner.invoke(cli, ["compare", GOOD_CARD, MINIMAL_CARD])
        assert "Winner" in result.output
        assert "DataPulse Analytics Agent" in result.output

    def test_compare_one_source_exits_one(self):
        result = self.runner.invoke(cli, ["compare", GOOD_CARD])
        assert result.exit_code == 1

    def test_compare_json_format(self):
        result = self.runner.invoke(cli, ["compare", GOOD_CARD, MINIMAL_CARD, "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "comparison" in data
        assert len(data["comparison"]) == 2

    def test_compare_three_cards(self):
        result = self.runner.invoke(cli, ["compare", GOOD_CARD, MINIMAL_CARD, GOOD_CARD])
        assert result.exit_code == 0


# ── CLI: version ───────────────────────────────────────────────────────────

class TestVersion:
    def test_version_flag(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output
