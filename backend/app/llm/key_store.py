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

    Encoding: the Fernet token bytes are stored as a lowercase hex string
    in the bytea column. Hex is used instead of base64 because PostgREST
    applies its own hex-prefix encoding to bytea values (\\x...), making
    a second base64 layer unreliable (padding length issues on round-trip).
    """
    encrypted = encrypt_key(plaintext_key)
    # Hex-encode: deterministic, no padding, no PostgREST bytea conflicts.
    encoded = encrypted.hex()

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

    # The value comes back from PostgREST as a string. It may arrive
    # hex-prefixed (\\x...) if PostgREST treats it as bytea, or as a plain
    # hex string. Handle both forms defensively.
    raw: str = resp.data["groq_api_key_encrypted"]
    if isinstance(raw, str) and raw.startswith("\\x"):
        # PostgREST bytea hex prefix: strip it and decode
        hex_str = raw[2:]
    else:
        hex_str = raw
    try:
        encrypted_bytes = bytes.fromhex(hex_str)
    except ValueError as exc:
        logger.error(
            "Stored key for user_id=%s has unexpected encoding: %r (first 20 chars)",
            user_id, hex_str[:20],
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored API key is corrupted — please re-enter it in Settings.",
        ) from exc
    plaintext = decrypt_key(encrypted_bytes)
    model = resp.data.get("groq_model")

    return plaintext, model


def delete_key(user_id: str) -> None:
    """Remove the user's stored Groq API key."""
    service_client().table("user_api_keys").delete().eq(
        "user_id", user_id
    ).execute()
    logger.info("Deleted Groq key for user_id=%s", user_id)

