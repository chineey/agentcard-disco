"""
Unit tests for the URL loader (load_from_url).

All HTTP calls are mocked via pytest-httpx or unittest.mock —
no real network calls are made.

Run with:  pytest tests/unit/test_url_loader.py -v
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import httpx

from agentcard_disco.parser import FetchError, ParseError, load, load_from_url

# ── Minimal valid card payload ─────────────────────────────────────────────

_VALID_CARD = {
    "name": "URL Test Agent",
    "url": "https://example.com/a2a",
    "version": "1.0.0",
    "capabilities": {"streaming": False, "pushNotifications": False},
    "skills": [
        {"id": "skill_1", "name": "Skill One", "description": "Does something useful"}
    ],
}


def _mock_response(status_code: int = 200, body: dict | None = None, text: str | None = None) -> MagicMock:
    """Build a mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    if text is not None:
        resp.content = text.encode()
    else:
        resp.content = json.dumps(body or _VALID_CARD).encode()
    return resp


# ── Tests: successful fetch ────────────────────────────────────────────────

class TestSuccessfulFetch:
    def test_loads_valid_card_from_url(self):
        with patch("httpx.get", return_value=_mock_response(200)):
            card = load_from_url("https://example.com/agent-card.json")
        assert card.name == "URL Test Agent"

    def test_smart_loader_detects_url(self):
        with patch("httpx.get", return_value=_mock_response(200)):
            card = load("https://example.com/agent-card.json")
        assert card.name == "URL Test Agent"

    def test_well_known_fallback(self):
        """If the exact URL returns non-200, tries /.well-known/agent-card.json."""
        responses = [
            _mock_response(404),           # first attempt fails
            _mock_response(200),           # well-known fallback succeeds
        ]
        with patch("httpx.get", side_effect=responses):
            card = load_from_url("https://example.com")
        assert card.name == "URL Test Agent"

    def test_no_well_known_fallback_when_path_explicit(self):
        """If URL already ends in agent-card.json, no fallback is attempted."""
        with patch("httpx.get", return_value=_mock_response(404)) as mock_get:
            with pytest.raises(FetchError):
                load_from_url("https://example.com/agent-card.json")
        assert mock_get.call_count == 1


# ── Tests: HTTP errors ─────────────────────────────────────────────────────

class TestHttpErrors:
    def test_404_raises_fetch_error(self):
        with patch("httpx.get", return_value=_mock_response(404)):
            with pytest.raises(FetchError, match="HTTP 404"):
                load_from_url("https://example.com/agent-card.json")

    def test_500_raises_fetch_error(self):
        with patch("httpx.get", return_value=_mock_response(500)):
            with pytest.raises(FetchError, match="HTTP 500"):
                load_from_url("https://example.com/agent-card.json")

    def test_timeout_raises_fetch_error(self):
        with patch("httpx.get", side_effect=httpx.TimeoutException("timed out")):
            with pytest.raises(FetchError, match="timed out"):
                load_from_url("https://example.com/agent-card.json")

    def test_network_error_raises_fetch_error(self):
        with patch("httpx.get", side_effect=httpx.RequestError("connection refused")):
            with pytest.raises(FetchError, match="Network error"):
                load_from_url("https://example.com/agent-card.json")


# ── Tests: bad response body ───────────────────────────────────────────────

class TestBadResponseBody:
    def test_invalid_json_raises_parse_error(self):
        with patch("httpx.get", return_value=_mock_response(200, text="not json {")):
            with pytest.raises(ParseError, match="Invalid JSON"):
                load_from_url("https://example.com/agent-card.json")

    def test_schema_violation_raises_parse_error(self):
        bad_card = {"name": "X"}  # missing required fields
        with patch("httpx.get", return_value=_mock_response(200, body=bad_card)):
            with pytest.raises(ParseError, match="Schema validation failed"):
                load_from_url("https://example.com/agent-card.json")

    def test_both_urls_fail_raises_last_error(self):
        """When both the direct URL and well-known fallback fail, FetchError is raised."""
        with patch("httpx.get", return_value=_mock_response(503)):
            with pytest.raises(FetchError):
                load_from_url("https://example.com")


# ── Tests: smart loader routing ───────────────────────────────────────────

class TestSmartLoader:
    def test_http_prefix_routes_to_url_loader(self):
        with patch("httpx.get", return_value=_mock_response(200)):
            card = load("http://example.com/agent-card.json")
        assert card.name == "URL Test Agent"

    def test_https_prefix_routes_to_url_loader(self):
        with patch("httpx.get", return_value=_mock_response(200)):
            card = load("https://example.com/agent-card.json")
        assert card.name == "URL Test Agent"

    def test_non_url_routes_to_file_loader(self, tmp_path):
        card_file = tmp_path / "card.json"
        card_file.write_text(json.dumps(_VALID_CARD))
        card = load(str(card_file))
        assert card.name == "URL Test Agent"
