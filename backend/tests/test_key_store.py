"""
Tests for app.llm.key_store — L5.0 acceptance criteria (offline portion).

The full accept criteria ("a user can set a key, GET confirms configured:
true without ever returning the raw value; round-trips correctly when
decrypted") requires live Supabase.  These tests cover the crypto layer
and the "no plaintext leaks" contract that can be verified offline.

Live integration (set → GET → real Groq call) is verified in L5.1.
"""
from __future__ import annotations

import os
import pytest

# Set a test encryption key BEFORE importing key_store (which reads settings
# at import time).  This avoids needing the real .env.
os.environ.setdefault(
    "ENCRYPTION_KEY",
    # A valid Fernet key for testing only — NOT a secret.
    "dGVzdGtleS0xMjM0NTY3ODkwMTIzNDU2Nzg5MDEyMzQ1Njc=",
)

from cryptography.fernet import Fernet

# Generate a proper Fernet key for tests and set it
_TEST_KEY = Fernet.generate_key().decode()
os.environ["ENCRYPTION_KEY"] = _TEST_KEY

# Reload settings to pick up the test key
from app.core.config import Settings
import app.core.config as config_mod
config_mod.settings = Settings()

from app.llm.key_store import encrypt_key, decrypt_key


# =========================================================================
# Crypto round-trip tests
# =========================================================================

class TestCryptoRoundTrip:
    """encrypt_key → decrypt_key must round-trip correctly."""

    def test_round_trip_basic(self):
        plaintext = "gsk_test1234567890abcdef"
        encrypted = encrypt_key(plaintext)
        decrypted = decrypt_key(encrypted)
        assert decrypted == plaintext

    def test_round_trip_special_chars(self):
        plaintext = "gsk_abc!@#$%^&*()_+-=[]{}|;':\",./<>?"
        encrypted = encrypt_key(plaintext)
        decrypted = decrypt_key(encrypted)
        assert decrypted == plaintext

    def test_encrypted_is_not_plaintext(self):
        """The encrypted output must not contain the plaintext."""
        plaintext = "gsk_test_secret_key_12345"
        encrypted = encrypt_key(plaintext)
        assert plaintext.encode() not in encrypted

    def test_different_encryptions_differ(self):
        """Two encryptions of the same key should produce different ciphertext
        (Fernet uses a random IV each time)."""
        plaintext = "gsk_same_key"
        e1 = encrypt_key(plaintext)
        e2 = encrypt_key(plaintext)
        assert e1 != e2
        # But both decrypt to the same value
        assert decrypt_key(e1) == decrypt_key(e2) == plaintext

    def test_encrypted_output_is_bytes(self):
        encrypted = encrypt_key("test")
        assert isinstance(encrypted, bytes)

    def test_decrypted_output_is_str(self):
        encrypted = encrypt_key("test")
        decrypted = decrypt_key(encrypted)
        assert isinstance(decrypted, str)


# =========================================================================
# Security contract tests
# =========================================================================

class TestSecurityContract:
    """Verify that the security contract holds at the API level."""

    def test_key_status_response_shape(self):
        """The KeyStatusResponse model should not have an api_key field."""
        from app.api.me import KeyStatusResponse
        fields = KeyStatusResponse.model_fields
        assert "api_key" not in fields
        assert "groq_api_key_encrypted" not in fields
        assert "configured" in fields
        assert "model" in fields

    def test_set_key_request_requires_api_key(self):
        """SetKeyRequest must require a non-empty api_key."""
        from app.api.me import SetKeyRequest
        with pytest.raises(Exception):
            SetKeyRequest(api_key="")  # min_length=1

    def test_set_key_request_accepts_valid_key(self):
        from app.api.me import SetKeyRequest
        req = SetKeyRequest(api_key="gsk_valid_key_123")
        assert req.api_key == "gsk_valid_key_123"
        assert req.model is None

    def test_set_key_request_with_model(self):
        from app.api.me import SetKeyRequest
        req = SetKeyRequest(api_key="gsk_key", model="llama-3.3-70b-versatile")
        assert req.model == "llama-3.3-70b-versatile"


# =========================================================================
# Hex encoding round-trip (store → fetch path)
# Tests the encoding layer used between store_key() and fetch_key_for_llm().
# =========================================================================

class TestHexEncoding:
    """Verify the hex encode/decode path used in store_key / fetch_key_for_llm."""

    def test_hex_round_trip(self):
        """encrypt → .hex() → bytes.fromhex() → decrypt must round-trip."""
        plaintext = "gsk_testkey_roundtrip"
        encrypted = encrypt_key(plaintext)
        encoded = encrypted.hex()          # store_key path
        recovered = bytes.fromhex(encoded) # fetch_key_for_llm path
        assert decrypt_key(recovered) == plaintext

    def test_hex_string_is_even_length(self):
        """Hex strings are always even length — no padding issues ever."""
        encrypted = encrypt_key("gsk_any_key")
        hex_str = encrypted.hex()
        assert len(hex_str) % 2 == 0

    def test_hex_string_is_valid_hex(self):
        """Hex output must only contain 0-9a-f characters."""
        import re
        encrypted = encrypt_key("gsk_any_key")
        hex_str = encrypted.hex()
        assert re.fullmatch(r"[0-9a-f]+", hex_str)

    def test_postgrest_prefix_stripped_correctly(self):
        """PostgREST may return bytea as \\x<hex>. fetch path must handle both."""
        plaintext = "gsk_postgrest_prefix_test"
        encrypted = encrypt_key(plaintext)
        hex_str = encrypted.hex()
        postgrest_form = "\\x" + hex_str
        # fetch_key_for_llm strips the \\x prefix
        raw = postgrest_form
        actual_hex = raw[2:] if raw.startswith("\\x") else raw
        assert decrypt_key(bytes.fromhex(actual_hex)) == plaintext

    def test_base64_regression(self):
        """Regression: base64 Fernet tokens can have length % 4 != 0 after
        PostgREST strips padding, causing binascii.Error on b64decode.
        The hex path has no such constraint — always works.
        """
        import base64
        encrypted = encrypt_key("gsk_regression_test")
        # Hex must always round-trip cleanly
        hex_encoded = encrypted.hex()
        assert bytes.fromhex(hex_encoded) == encrypted
        # Demonstrate that stripped base64 can fail (the original bug)
        b64 = base64.b64encode(encrypted).decode("ascii")
        stripped = b64.rstrip("=")
        if len(stripped) % 4 != 0:
            with pytest.raises(Exception):
                base64.b64decode(stripped, validate=True)
