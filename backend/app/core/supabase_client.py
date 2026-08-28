"""
Supabase client factory for AskYourData.ai.

Two clients, two trust levels:
  - service_client()  — service-role key, bypasses RLS, for trusted internal
                        operations (storage upload, user profile creation, etc.)
  - rls_client(jwt)   — anon key + user JWT, fully RLS-enforced, for all
                        user-facing database reads/writes.

IMPORTANT: never use the service client on user-supplied data paths where
RLS should be the guard. Only use it where you have already verified the
caller's permissions in application code.
"""
from __future__ import annotations

from supabase import Client, create_client

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Singletons — created lazily on first use so the app boots even when env
# vars aren't set yet (tests can override settings before calling these).
# ---------------------------------------------------------------------------
_service_client: Client | None = None


def service_client() -> Client:
    """Return the shared service-role Supabase client (bypasses RLS)."""
    global _service_client
    if _service_client is None:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set before "
                "calling service_client()."
            )
        _service_client = create_client(
            settings.supabase_url, settings.supabase_service_role_key
        )
        logger.info("Supabase service-role client initialised.")
    return _service_client


def rls_client(jwt: str) -> Client:
    """
    Return a per-request Supabase client scoped to the caller's JWT.

    The anon key is used to create the client (so Supabase Auth policy
    applies), then the user's JWT is injected into the PostgREST auth
    header so that Postgres RLS policies evaluate as auth.uid() == user.
    """
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_ANON_KEY must be set before "
            "calling rls_client()."
        )
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    client.postgrest.auth(jwt)
    return client
