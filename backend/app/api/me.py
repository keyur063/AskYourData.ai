"""
Per-user Groq API key management endpoints.

  POST   /me/groq-key    — set/update (encrypts before storing)
  GET    /me/groq-key    — returns {configured, model} only, never the raw key
  DELETE /me/groq-key    — removes the key

Implemented in ticket L5.0 (Session 5).

SECURITY: the raw API key must never be logged, returned, or stored
plaintext. All storage goes through app.llm.key_store which applies
Fernet encryption with ENCRYPTION_KEY before writing to user_api_keys.
"""
from fastapi import APIRouter

router = APIRouter()

# TODO L5.0: POST /me/groq-key
# TODO L5.0: GET  /me/groq-key
# TODO L5.0: DELETE /me/groq-key
