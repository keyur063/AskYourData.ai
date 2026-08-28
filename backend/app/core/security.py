"""
JWT verification middleware for AskYourData.ai.

Supabase issues standard JWTs for authenticated users. This module
provides a FastAPI dependency (`require_user`) that:
  1. Extracts the Bearer token from the Authorization header.
  2. Verifies it by calling Supabase Auth's /user endpoint (no local
     secret needed — Supabase validates and returns the user object).
  3. Returns the verified user_id (UUID string) so endpoints can use it.
  4. Raises HTTP 401 for missing, malformed, or expired tokens.

Usage in an endpoint:
    @router.get("/protected")
    async def protected(user_id: str = Depends(require_user)):
        ...
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.logging import get_logger
from app.core.supabase_client import service_client

logger = get_logger(__name__)

_bearer = HTTPBearer(auto_error=False)


async def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """
    FastAPI dependency — resolves to the verified user_id string.
    Raises 401 if the token is absent, malformed, or rejected by Supabase.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        # Use the service client's auth object to verify the token.
        # This calls GET /auth/v1/user with the JWT as Bearer — Supabase
        # rejects expired / tampered tokens with a non-2xx response.
        response = service_client().auth.get_user(token)
        user = response.user
        if user is None:
            raise ValueError("No user in response")
        return str(user.id)
    except Exception as exc:
        logger.warning("JWT verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
