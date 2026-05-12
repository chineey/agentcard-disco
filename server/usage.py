"""
server/usage.py — usage logging to Supabase.

Writes one row to usage_logs after every scoring request.
Logging is fire-and-forget: failures are silently swallowed so a
logging hiccup never breaks a real request.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from server.auth import _get_supabase


def log_request(
    key_hash: Optional[str],
    owner: Optional[str],
    endpoint: str,
    deep: bool,
    status_code: int,
) -> None:
    """
    Insert a row into usage_logs.
    Called as a background task so it never slows down the response.
    """
    try:
        supabase = _get_supabase()
        supabase.table("usage_logs").insert({
            "key_hash":    key_hash,
            "owner":       owner,
            "endpoint":    endpoint,
            "deep":        deep,
            "status_code": status_code,
        }).execute()
    except Exception:
        pass   # never let logging break the request