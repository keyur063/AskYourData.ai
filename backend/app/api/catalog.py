"""
Catalog router — GET /catalog/tables, GET /catalog/tables/{id}.

L3.1 implementation.

GET /workspaces/{workspace_id}/catalog/tables
  → list of catalog_tables visible to the caller (RLS-enforced)

GET /workspaces/{workspace_id}/catalog/tables/{table_id}
  → single table + nested columns array
"""
from typing import Annotated
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.logging import get_logger
from app.core.security import CurrentUser, require_user
from app.catalog.service import get_tables, get_table_with_columns

logger = get_logger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class CatalogTableSummary(BaseModel):
    id: UUID
    workspace_id: UUID
    file_id: UUID
    name: str
    row_count: int | None = None
    created_at: datetime


class CatalogColumnOut(BaseModel):
    id: UUID
    table_id: UUID
    workspace_id: UUID
    name: str
    data_type: str
    nullable: bool
    sample_values: str | None = None  # JSON string of sample values


class CatalogTableDetail(BaseModel):
    id: UUID
    workspace_id: UUID
    file_id: UUID
    name: str
    row_count: int | None = None
    created_at: datetime
    columns: list[CatalogColumnOut] = []


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/workspaces/{workspace_id}/catalog/tables",
    response_model=list[CatalogTableSummary],
)
async def list_catalog_tables(
    workspace_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_user)],
):
    """List all catalog tables in a workspace."""
    tables = get_tables(str(workspace_id), current_user.jwt)
    return tables


@router.get(
    "/workspaces/{workspace_id}/catalog/tables/{table_id}",
    response_model=CatalogTableDetail,
)
async def get_catalog_table(
    workspace_id: UUID,
    table_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_user)],
):
    """Get a single catalog table with its columns."""
    table = get_table_with_columns(str(workspace_id), str(table_id), current_user.jwt)
    if table is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Table not found.",
        )
    return table
