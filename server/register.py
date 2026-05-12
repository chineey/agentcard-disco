"""
server/register.py — API key self-service registration.

Flow:
  1. User POSTs their email to POST /v1/register
  2. Server generates a random key, hashes it, stores hash in Supabase
  3. Server emails the raw key to the user via Resend
  4. Raw key is never stored anywhere — only the hash

One key per email. If the email already has an active key, we resend it
by revoking the old one and issuing a fresh key.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from functools import lru_cache

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr

from server.auth import _get_supabase

router = APIRouter()

_RESEND_API_URL = "https://api.resend.com/emails"
_KEY_PREFIX = "acd_"   # makes keys recognisable: acd_<32 random hex chars>


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_raw_key() -> str:
    """Generate a random, prefixed API key."""
    return _KEY_PREFIX + secrets.token_hex(32)


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def _send_key_email(to_email: str, raw_key: str) -> None:
    """Send the raw API key to the user via Resend."""
    resend_key = os.environ.get("RESEND_API_KEY")
    from_email = os.environ.get("RESEND_FROM_EMAIL", "onboarding@resend.dev")

    if not resend_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email service is not configured on this server.",
        )

    html_body = f"""
    <div style="font-family: sans-serif; max-width: 520px; margin: 0 auto;">
      <h2>Your AgentCard Disco API Key</h2>
      <p>Here is your API key. Keep it safe — we won't show it again.</p>
      <div style="background:#f4f4f4; padding:16px; border-radius:8px;
                  font-family:monospace; font-size:15px; word-break:break-all;">
        {raw_key}
      </div>
      <p style="margin-top:24px;">To score an Agent Card, include the key in your request header:</p>
      <pre style="background:#f4f4f4; padding:12px; border-radius:8px; font-size:13px;">
X-API-Key: {raw_key}</pre>
      <p>Visit <a href="https://agentcard-disco.onrender.com/docs">the API docs</a>
         to get started.</p>
      <hr style="margin-top:32px; border:none; border-top:1px solid #eee;">
      <p style="font-size:12px; color:#999;">AgentCard Disco — A2A protocol scoring</p>
    </div>
    """

    async with httpx.AsyncClient() as client:
        response = await client.post(
            _RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {resend_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": from_email,
                "to": [to_email],
                "subject": "Your AgentCard Disco API Key",
                "html": html_body,
            },
            timeout=10,
        )

    if response.status_code not in (200, 201):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to send email: {response.text}",
        )


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: EmailStr

    model_config = {
        "json_schema_extra": {
            "example": {"email": "alice@example.com"}
        }
    }


# ---------------------------------------------------------------------------
# POST /v1/register
# ---------------------------------------------------------------------------

@router.post("/register", tags=["Auth"])
async def register(payload: RegisterRequest):
    """
    Request a free API key.

    Supply an email address. A fresh key will be generated, stored
    (as a hash only), and emailed to you. One active key per email —
    calling this again revokes the previous key and issues a new one.
    """
    supabase = _get_supabase()
    email = payload.email.lower().strip()

    # Revoke any existing key for this email so there's only ever one active key
    supabase.table("api_keys").update({"is_active": False}).eq("owner", email).execute()

    # Generate and store the new key
    raw_key = _generate_raw_key()
    key_hash = _hash_key(raw_key)

    supabase.table("api_keys").insert({
        "key_hash": key_hash,
        "owner": email,
        "tier": "free",
        "is_active": True,
    }).execute()

    # Email the raw key — only time it ever leaves the server
    await _send_key_email(email, raw_key)

    return {
        "message": "API key sent — check your inbox.",
        "email": email,
    }
