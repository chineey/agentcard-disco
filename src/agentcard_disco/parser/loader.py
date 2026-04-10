"""
AgentCard parser.

Supports loading from:
  - Local .json file path
  - Remote URL (fetched via httpx with timeout + redirect handling)

Returns a validated AgentCard model or raises a structured ParseError.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from agentcard_disco.models import AgentCard


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ParseError(Exception):
    """Raised when a card cannot be parsed or validated."""

    def __init__(self, message: str, raw: dict | None = None) -> None:
        super().__init__(message)
        self.raw = raw  # preserve raw dict for partial analysis if needed


class FetchError(Exception):
    """Raised when a remote card URL cannot be retrieved."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_dict(raw: dict[str, Any]) -> AgentCard:
    """Validate a raw dict against the AgentCard schema."""
    try:
        return AgentCard.model_validate(raw)
    except ValidationError as exc:
        errors = exc.errors(include_url=False)
        summary = "; ".join(
            f"{' -> '.join(str(loc) for loc in e['loc'])}: {e['msg']}"
            for e in errors
        )
        raise ParseError(
            f"Schema validation failed ({len(errors)} error(s)): {summary}",
            raw=raw,
        ) from exc


def _load_json_bytes(data: bytes, source: str) -> dict[str, Any]:
    """Parse raw bytes as JSON, raising ParseError on failure."""
    try:
        return json.loads(data)
    except json.JSONDecodeError as exc:
        raise ParseError(
            f"Invalid JSON from {source!r}: {exc.msg} (line {exc.lineno}, col {exc.colno})"
        ) from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_from_file(path: str | Path) -> AgentCard:
    """
    Load and validate an AgentCard from a local JSON file.

    Args:
        path: Path to the .json file.

    Returns:
        Validated AgentCard instance.

    Raises:
        ParseError: If the file cannot be read, decoded, or validated.
    """
    p = Path(path).expanduser().resolve()

    if not p.exists():
        raise ParseError(f"File not found: {p}")
    if not p.is_file():
        raise ParseError(f"Path is not a file: {p}")

    try:
        raw_bytes = p.read_bytes()
    except OSError as exc:
        raise ParseError(f"Cannot read file {p}: {exc}") from exc

    raw = _load_json_bytes(raw_bytes, str(p))
    return _parse_dict(raw)


def load_from_url(
    url: str,
    *,
    timeout: float = 10.0,
    follow_redirects: bool = True,
) -> AgentCard:
    """
    Fetch and validate an AgentCard from a remote URL.

    The function tries the exact URL first, then falls back to appending
    '/.well-known/agent-card.json' if the original URL returns a non-JSON
    response (helpful when users pass just a base domain).

    Args:
        url: Full URL or base domain to fetch from.
        timeout: Request timeout in seconds.
        follow_redirects: Whether to follow HTTP redirects.

    Returns:
        Validated AgentCard instance.

    Raises:
        FetchError: If the URL cannot be reached or returns a bad status.
        ParseError: If the fetched content is not valid JSON or schema.
    """
    headers = {
        "Accept": "application/json",
        "User-Agent": "agentcard-disco/0.1.0 (https://github.com/chinemeze/agentcard-disco)",
    }

    candidates = [url]
    # Auto-append well-known path if not already present
    if not url.rstrip("/").endswith(("agent-card.json", "agent.json")):
        base = url.rstrip("/")
        candidates.append(f"{base}/.well-known/agent-card.json")

    last_exc: Exception | None = None
    for candidate in candidates:
        try:
            response = httpx.get(
                candidate,
                timeout=timeout,
                follow_redirects=follow_redirects,
                headers=headers,
            )
        except httpx.TimeoutException:
            last_exc = FetchError(f"Request timed out after {timeout}s: {candidate}")
            continue
        except httpx.RequestError as exc:
            last_exc = FetchError(f"Network error fetching {candidate!r}: {exc}")
            continue

        if response.status_code == 200:
            raw = _load_json_bytes(response.content, candidate)
            return _parse_dict(raw)

        last_exc = FetchError(
            f"HTTP {response.status_code} from {candidate!r}"
        )

    raise last_exc or FetchError(f"Could not retrieve a valid Agent Card from {url!r}")


def load(source: str) -> AgentCard:
    """
    Smart loader: detects whether source is a URL or local file path.

    Args:
        source: A file path string or an http(s):// URL.

    Returns:
        Validated AgentCard instance.
    """
    if source.startswith(("http://", "https://")):
        return load_from_url(source)
    return load_from_file(source)
