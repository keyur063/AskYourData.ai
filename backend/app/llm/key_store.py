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
from app.core.config import settings


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


# TODO L5.0: implement store_key(user_id, plaintext_key, model) -> None
#   — calls encrypt_key(), upserts into user_api_keys via service_client()
# TODO L5.0: implement get_key_status(user_id) -> dict  {configured, model}
#   — queries user_api_keys via service_client(), returns NO plaintext
# TODO L5.0: implement fetch_key_for_llm(user_id) -> str
#   — fetches encrypted bytes via service_client(), calls decrypt_key(),
#     raises a user-facing "No Groq key configured" HTTPException if absent
# TODO L5.0: implement delete_key(user_id) -> None
