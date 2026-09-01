"""
Per-user Groq API key store — encrypt/decrypt/fetch.

Implemented in ticket L5.0 (Session 5).

Uses cryptography.fernet.Fernet with the ENCRYPTION_KEY env var.
The Fernet key must be set before any of these functions are called;
the functions raise a clear RuntimeError if it isn't.

SECURITY contract (must hold everywhere this module is used):
  - decrypt_key() result is used in-memory for one LLM call, then discarded.
  - The plaintext key is NEVER logged, returned in an API response, or
    stored anywhere except the encrypted column in user_api_keys.
  - If ENCRYPTION_KEY is rotated, all stored keys must be re-encrypted —
    add a migration script at that point (not needed for lean scope).
"""
from __future__ import annotations

import base64

from fastapi import HTTPException, status

from app.core.config import settings
from app.core.logging import get_logger
from app.core.supabase_client import service_client

logger = get_logger(__name__)


def _get_fernet():
    """Return a Fernet instance using ENCRYPTION_KEY from settings.

    Raises RuntimeError if ENCRYPTION_KEY is not set — this makes
    misconfiguration fail loudly at call time, not silently.
    """
    from cryptography.fernet import Fernet

    if not settings.encryption_key:
        raise RuntimeError(
            "ENCRYPTION_KEY is not set. Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(settings.encryption_key.encode())


def encrypt_key(plaintext_key: str) -> bytes:
    """Encrypt a plaintext Groq API key. Returns Fernet token bytes."""
    return _get_fernet().encrypt(plaintext_key.encode())


def decrypt_key(encrypted_bytes: bytes) -> str:
    """Decrypt stored Fernet token bytes. Returns plaintext key string.

    Use the result immediately for an LLM call — do not hold onto it.
    """
    return _get_fernet().decrypt(encrypted_bytes).decode()


# ---------------------------------------------------------------------------
# Database operations (all via service_client — bypasses RLS)
# ---------------------------------------------------------------------------

def store_key(user_id: str, plaintext_key: str, model: str | None = None) -> None:
    """Encrypt and upsert a Groq API key for the given user.

    The plaintext key is encrypted immediately and never stored or
    logged in cleartext.
    """
    encrypted = encrypt_key(plaintext_key)
    # Store as base64 text so it survives JSON / PostgREST round-tripping
    # (bytea columns via PostgREST use base64 with a \\x prefix, which is
    # fragile; storing as text column would require a schema change).
    encoded = base64.b64encode(encrypted).decode("ascii")

    row = {
        "user_id": user_id,
        "groq_api_key_encrypted": encoded,
        "groq_model": model,
    }

    # Upsert — insert if absent, update if present.
    service_client().table("user_api_keys").upsert(
        row, on_conflict="user_id"
    ).execute()

    logger.info("Stored encrypted Groq key for user_id=%s", user_id)


def get_key_status(user_id: str) -> dict:
    """Return {configured: bool, model: str|None} for the given user.

    NEVER returns the raw key — only whether one is set.
    """
    resp = (
        service_client()
        .table("user_api_keys")
        .select("groq_model")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if resp.data is None:
        return {"configured": False, "model": None}
    return {"configured": True, "model": resp.data.get("groq_model")}


def fetch_key_for_llm(user_id: str) -> tuple[str, str | None]:
    """Fetch and decrypt the user's Groq API key for an LLM call.

    Returns (plaintext_key, model_override_or_none).

    Raises:
        HTTPException 402: if the user has no API key configured.
    """
    resp = (
        service_client()
        .table("user_api_keys")
        .select("groq_api_key_encrypted, groq_model")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if resp.data is None:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="No Groq API key configured — add one in Settings.",
        )

    encrypted_b64: str = resp.data["groq_api_key_encrypted"]
    encrypted_bytes = base64.b64decode(encrypted_b64)
    plaintext = decrypt_key(encrypted_bytes)
    model = resp.data.get("groq_model")

    return plaintext, model


def delete_key(user_id: str) -> None:
    """Remove the user's stored Groq API key."""
    service_client().table("user_api_keys").delete().eq(
        "user_id", user_id
    ).execute()
    logger.info("Deleted Groq key for user_id=%s", user_id)

