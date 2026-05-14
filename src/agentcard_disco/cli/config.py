"""
cli/config.py — local API key storage for agentcard-disco.

Saves the user's API key to ~/.agentcard-disco/config.json so --deep
works without any extra config after a one-time `agentcard-disco auth <key>`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_CONFIG_DIR  = Path.home() / ".agentcard-disco"
_CONFIG_FILE = _CONFIG_DIR / "config.json"
_API_BASE    = "https://agentcard-disco.onrender.com"


def save_api_key(key: str) -> None:
    """Persist the raw API key to ~/.agentcard-disco/config.json."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config = _load_config()
    config["api_key"] = key
    _CONFIG_FILE.write_text(json.dumps(config, indent=2))
    # Restrict file permissions so other users can't read it
    _CONFIG_FILE.chmod(0o600)


def get_api_key() -> str | None:
    """Return the stored API key, or None if not configured."""
    config = _load_config()
    return config.get("api_key") or os.environ.get("AGENTCARD_DISCO_API_KEY")


def get_api_base() -> str:
    """Return the API base URL (overridable via env var for self-hosting)."""
    return os.environ.get("AGENTCARD_DISCO_API_BASE", _API_BASE)


def _load_config() -> dict:
    if _CONFIG_FILE.exists():
        try:
            return json.loads(_CONFIG_FILE.read_text())
        except Exception:
            return {}
    return {}