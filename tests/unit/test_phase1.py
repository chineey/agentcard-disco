"""
Unit tests for Phase 1: models + parser.

Run with:  pytest tests/unit/test_phase1.py -v
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from agentcard_disco.models import AgentCard, AgentSkill
from agentcard_disco.parser import ParseError, load_from_file

FIXTURES = Path(__file__).parent.parent / "fixtures"


# ---------------------------------------------------------------------------
# Model: AgentSkill
# ---------------------------------------------------------------------------


class TestAgentSkill:
    def test_minimal_valid_skill(self):
        skill = AgentSkill(id="foo", name="Foo", description="Does foo things")
        assert skill.id == "foo"
        assert skill.tags == []
        assert skill.examples == []

    def test_string_tag_coerced_to_list(self):
        skill = AgentSkill(id="x", name="X", description="X skill", tags="single-tag")
        assert skill.tags == ["single-tag"]

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            AgentSkill(id="x")  # name + description missing


# ---------------------------------------------------------------------------
# Model: AgentCard
# ---------------------------------------------------------------------------


class TestAgentCard:
    def _base_payload(self, **overrides):
        payload = {
            "name": "Test Agent",
            "url": "https://example.com/a2a",
            "version": "1.0.0",
            "capabilities": {"streaming": False, "pushNotifications": False},
            "skills": [
                {
                    "id": "test_skill",
                    "name": "Test Skill",
                    "description": "A test skill for unit tests",
                }
            ],
        }
        payload.update(overrides)
        return payload

    def test_valid_minimal_card(self):
        card = AgentCard.model_validate(self._base_payload())
        assert card.name == "Test Agent"
        assert card.is_semver is True

    def test_missing_required_name(self):
        p = self._base_payload()
        del p["name"]
        with pytest.raises(ValidationError):
            AgentCard.model_validate(p)

    def test_missing_skills_rejected(self):
        p = self._base_payload(skills=[])
        with pytest.raises(ValidationError):
            AgentCard.model_validate(p)

    def test_duplicate_skill_ids_rejected(self):
        p = self._base_payload(
            skills=[
                {"id": "dupe", "name": "Skill A", "description": "A"},
                {"id": "dupe", "name": "Skill B", "description": "B"},
            ]
        )
        with pytest.raises(ValidationError, match="duplicate skill IDs"):
            AgentCard.model_validate(p)

    def test_non_semver_version_still_accepted(self):
        card = AgentCard.model_validate(self._base_payload(version="1"))
        assert card.is_semver is False

    def test_is_semver_true(self):
        card = AgentCard.model_validate(self._base_payload(version="2.3.1"))
        assert card.is_semver is True

    def test_streaming_property(self):
        card = AgentCard.model_validate(
            self._base_payload(capabilities={"streaming": True, "pushNotifications": False})
        )
        assert card.has_streaming is True

    def test_all_tags_aggregation(self):
        p = self._base_payload(
            skills=[
                {"id": "s1", "name": "S1", "description": "Skill 1", "tags": ["a", "b"]},
                {"id": "s2", "name": "S2", "description": "Skill 2", "tags": ["c"]},
            ]
        )
        card = AgentCard.model_validate(p)
        assert set(card.all_tags) == {"a", "b", "c"}

    def test_extra_fields_tolerated(self):
        """Unknown fields should not cause a validation error (forward compat)."""
        p = self._base_payload(unknownFutureField="some_value")
        card = AgentCard.model_validate(p)
        assert card is not None


# ---------------------------------------------------------------------------
# Parser: load_from_file
# ---------------------------------------------------------------------------


class TestParser:
    def test_load_good_card(self):
        card = load_from_file(FIXTURES / "good_card.json")
        assert card.name == "DataPulse Analytics Agent"
        assert len(card.skills) == 3
        assert card.has_streaming is True
        assert card.is_semver is True

    def test_load_minimal_card(self):
        card = load_from_file(FIXTURES / "minimal_card.json")
        assert card.name == "My Agent"
        assert len(card.skills) == 1
        assert card.is_semver is False

    def test_file_not_found(self):
        with pytest.raises(ParseError, match="File not found"):
            load_from_file("/nonexistent/path/card.json")

    def test_invalid_json(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{ not valid json }")
        with pytest.raises(ParseError, match="Invalid JSON"):
            load_from_file(bad)

    def test_invalid_schema(self, tmp_path):
        bad = tmp_path / "no_skills.json"
        bad.write_text('{"name": "X", "url": "https://x.com", "version": "1.0.0", "capabilities": {}}')
        with pytest.raises(ParseError, match="Schema validation failed"):
            load_from_file(bad)
