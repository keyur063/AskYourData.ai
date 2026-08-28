"""
JWT verification middleware for AskYourData.ai.

Supabase issues standard JWTs for authenticated users. This module provides:

  CurrentUser — dataclass holding the verified user_id and raw JWT.
                Endpoints that need rls_client() (read paths) use the jwt
                field; write paths that use service_client() use user_id.

  require_user — FastAPI dependency that:
    1. Extracts the Bearer token from the Authorization header.
    2. Verifies it via Supabase Auth's /user endpoint.
    3. Returns CurrentUser(user_id, jwt).
    4. Raises HTTP 401 for missing, malformed, or expired tokens.

Usage in an endpoint:
    from app.core.security import CurrentUser, require_user

    @router.get("/protected")
    async def protected(current_user: Annotated[CurrentUser, Depends(require_user)]):
        client = rls_client(current_user.jwt)   # RLS-enforced reads
        ...
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.logging import get_logger
from app.core.supabase_client import service_client

logger = get_logger(__name__)

_bearer = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    """Verified caller identity after JWT validation."""
    user_id: str  # UUID string — use for DB writes and llm_usage logging
    jwt: str      # raw token — pass to rls_client() for RLS-enforced reads


async def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    """
    FastAPI dependency — resolves to a verified CurrentUser.
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
        # Calls GET /auth/v1/user — Supabase rejects expired/tampered tokens.
        response = service_client().auth.get_user(token)
        user = response.user
        if user is None:
            raise ValueError("No user in response")
        return CurrentUser(user_id=str(user.id), jwt=token)
    except Exception as exc:
        logger.warning("JWT verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
