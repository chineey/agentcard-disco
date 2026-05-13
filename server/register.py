"""
server/register.py — API key self-service registration.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import traceback

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr

from server.auth import _get_supabase

router = APIRouter()
logger = logging.getLogger(__name__)

_RESEND_API_URL = "https://api.resend.com/emails"
_KEY_PREFIX = "acd_"


def _generate_raw_key() -> str:
    return _KEY_PREFIX + secrets.token_hex(32)


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def _send_key_email(to_email: str, raw_key: str) -> None:
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


class RegisterRequest(BaseModel):
    email: EmailStr

    model_config = {
        "json_schema_extra": {
            "example": {"email": "alice@example.com"}
        }
    }


@router.post("/register", tags=["Auth"])
async def register(payload: RegisterRequest):
    """
    Request a free API key. Supply an email — a key will be generated,
    stored as a hash in Supabase, and emailed to you.
    """
    try:
        supabase = _get_supabase()
        email = payload.email.lower().strip()

        logger.info(f"Register request for: {email}")

        # Revoke any existing key for this email
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

        logger.info(f"Key stored for: {email}, sending email...")

        # Email the raw key
        await _send_key_email(email, raw_key)

        logger.info(f"Email sent successfully to: {email}")

        return {
            "message": "API key sent — check your inbox.",
            "email": email,
            "api_key": raw_key,  
        }

    except HTTPException:
        raise  # re-raise FastAPI exceptions as-is

    except Exception as e:
        # Log the full traceback so it shows up in Render logs
        logger.error(f"Register failed for {payload.email}:\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}",
        )