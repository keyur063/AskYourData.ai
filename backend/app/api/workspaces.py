"""
Workspaces router — POST /workspaces, GET /workspaces.

L1.3 implementation.

POST /workspaces:
  Creates a workspace. The calling user is set as `created_by`; the
  `on_workspace_created` trigger in the DB auto-inserts them into
  `workspace_members` as 'owner'. Uses service_client for the insert
  (the workspaces RLS policy only covers SELECT — not INSERT — so the
  anon-key client can't insert even with a valid JWT).

GET /workspaces:
  Returns workspaces visible to the calling user. Uses rls_client(jwt)
  so the DB-level RLS policy (`ws_isolation_workspaces`) enforces isolation
  automatically: a user never sees workspaces they're not a member of, even
  if they guess another workspace's UUID.
"""
from typing import Annotated
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.core.security import CurrentUser, require_user
from app.core.supabase_client import rls_client, service_client

logger = get_logger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, strip_whitespace=True)


class WorkspaceOut(BaseModel):
    id: UUID
    name: str
    created_by: UUID
    created_at: datetime


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", status_code=status.HTTP_201_CREATED, response_model=WorkspaceOut)
async def create_workspace(
    body: WorkspaceCreate,
    current_user: Annotated[CurrentUser, Depends(require_user)],
):
    """
    Create a new workspace.
    The calling user becomes the owner automatically (DB trigger).
    """
    try:
        result = (
            service_client()
            .table("workspaces")
            .insert({"name": body.name, "created_by": current_user.user_id})
            .execute()
        )
    except Exception as exc:
        logger.error("create_workspace failed user=%s err=%s", current_user.user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create workspace.",
        ) from exc

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Workspace insert returned no data.",
        )

    ws = result.data[0]
    logger.info("workspace created id=%s user=%s", ws["id"], current_user.user_id)
    return ws


@router.get("", response_model=list[WorkspaceOut])
async def list_workspaces(
    current_user: Annotated[CurrentUser, Depends(require_user)],
):
    """
    List workspaces the calling user is a member of.
    RLS on `workspaces` enforces isolation — no manual filtering needed.
    """
    try:
        result = (
            rls_client(current_user.jwt)
            .table("workspaces")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
    except Exception as exc:
        logger.error("list_workspaces failed user=%s err=%s", current_user.user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list workspaces.",
        ) from exc

    return result.data

