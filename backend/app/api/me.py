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
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.core.security import CurrentUser, require_user
from app.llm.key_store import store_key, get_key_status, delete_key

logger = get_logger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class SetKeyRequest(BaseModel):
    api_key: str = Field(..., min_length=1, description="Groq API key (plaintext over HTTPS).")
    model: str | None = Field(None, description="Optional Groq model override.")


class KeyStatusResponse(BaseModel):
    configured: bool
    model: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/me/groq-key", response_model=KeyStatusResponse, status_code=200)
async def set_groq_key(
    body: SetKeyRequest,
    current_user: Annotated[CurrentUser, Depends(require_user)],
):
    """Set or update the caller's Groq API key.

    The key is encrypted (Fernet) before storage and NEVER logged or
    returned. After storing, returns the same shape as GET (configured
    status + model) so the frontend can update UI state in one call.
    """
    store_key(current_user.user_id, body.api_key, body.model)
    logger.info("Groq key set for user_id=%s", current_user.user_id)
    return KeyStatusResponse(configured=True, model=body.model)


@router.get("/me/groq-key", response_model=KeyStatusResponse)
async def get_groq_key(
    current_user: Annotated[CurrentUser, Depends(require_user)],
):
    """Check whether the caller has a Groq API key configured.

    Returns {configured: true/false, model: "..." | null}.
    NEVER returns the raw key.
    """
    status = get_key_status(current_user.user_id)
    return KeyStatusResponse(**status)


@router.delete("/me/groq-key", status_code=204)
async def remove_groq_key(
    current_user: Annotated[CurrentUser, Depends(require_user)],
):
    """Remove the caller's stored Groq API key."""
    delete_key(current_user.user_id)
    logger.info("Groq key removed for user_id=%s", current_user.user_id)

