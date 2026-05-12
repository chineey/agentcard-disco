"""
auth.py — API key verification and rate limiting.

Keys are stored in Supabase as SHA-256 hashes.
The raw key is never stored — only its hash is compared.

Supabase table schema (run this SQL in your Supabase project once):

    CREATE TABLE api_keys (
        id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        key_hash    text UNIQUE NOT NULL,
        owner       text,
        tier        text DEFAULT 'free',   -- 'free' | 'pro'
        is_active   boolean DEFAULT true,
        created_at  timestamptz DEFAULT now()
    );

To add a key:
    INSERT INTO api_keys (key_hash, owner, tier)
    VALUES (encode(sha256('your-raw-key'::bytea), 'hex'), 'Alice', 'pro');
"""

import hashlib
import os
from functools import lru_cache
from typing import Optional

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader
from slowapi import Limiter
from slowapi.util import get_remote_address
from supabase import Client, create_client


# ---------------------------------------------------------------------------
# Supabase client (singleton via lru_cache)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_supabase() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]   # service role — bypasses RLS
    return create_client(url, key)


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def hash_key(raw_key: str) -> str:
    """Return the SHA-256 hex digest of a raw API key."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


# ---------------------------------------------------------------------------
# FastAPI dependency — validates the key and returns the row
# ---------------------------------------------------------------------------

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(raw_key: Optional[str] = Security(_API_KEY_HEADER)) -> dict:
    """
    Dependency injected into every protected route.

    1. Requires the X-API-Key request header.
    2. Hashes the value with SHA-256.
    3. Looks it up in the Supabase api_keys table.
    4. Rejects missing / unknown / inactive keys.

    Returns the full api_keys row so routes can check tier / owner if needed.
    """
    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header.",
        )

    key_hash = hash_key(raw_key)
    supabase = _get_supabase()

    # supabase-py v2: .single() raises APIError (PGRST116) when 0 rows match —
    # it does NOT return None. We must catch the exception, not check result.data.
    try:
        result = (
            supabase.table("api_keys")
            .select("*")
            .eq("key_hash", key_hash)
            .single()
            .execute()
        )
    except Exception:
        # Any exception here means the key wasn't found (or a DB error).
        # Either way, the key is not valid.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )

    row = result.data
    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )

    if not row.get("is_active", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key is inactive.",
        )

    return row


# ---------------------------------------------------------------------------
# Rate limiter (slowapi — per-key, not per-IP)
# ---------------------------------------------------------------------------

def _rate_limit_key(request) -> str:
    """Identify requests by their API key; fall back to IP."""
    return request.headers.get("X-API-Key") or get_remote_address(request)


# Default: 60 requests/hour per key.
# Individual routes can override with a stricter @limiter.limit() decorator.
limiter = Limiter(key_func=_rate_limit_key, default_limits=["60/hour"])
