"""
Files router — POST /workspaces/{id}/files, GET /workspaces/{id}/files/{file_id}.

L2.1 implementation.

Upload flow (synchronous — one request/response cycle):
  1. Validate file (extension, size)
  2. Parse CSV (pandas)
  3. Compute content hash (SHA-256 of raw bytes)
  4. Check for duplicate (same workspace + hash)
  5. Upload raw bytes to Supabase Storage
  6. Insert `files` row with state = READY
  7. Return the file record

The file transitions through UPLOADING → PROCESSING → READY in code, but
since the processing is synchronous, the insert is done directly as READY
(or FAILED on error) — no async polling needed for lean scope.
"""
import hashlib
from typing import Annotated
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.core.logging import get_logger
from app.core.security import CurrentUser, require_user
from app.core.supabase_client import rls_client, service_client
from app.ingestion.parser import parse_csv
from app.ingestion.schema_inference import infer_schema
from app.ingestion.storage import upload_file
from app.ingestion.validators import validate_csv_upload
from app.catalog.service import create_catalog_entry

logger = get_logger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class FileOut(BaseModel):
    id: UUID
    workspace_id: UUID
    filename: str
    storage_path: str
    content_hash: str
    size_bytes: int
    row_count: int | None = None
    state: str
    error_message: str | None = None
    uploaded_by: UUID
    created_at: datetime


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/workspaces/{workspace_id}/files",
    status_code=status.HTTP_201_CREATED,
    response_model=FileOut,
)
async def upload_csv(
    workspace_id: UUID,
    file: UploadFile,
    current_user: Annotated[CurrentUser, Depends(require_user)],
):
    """
    Upload a CSV file to a workspace.

    Synchronous: validates, parses, stores, and returns READY in one call.
    Rejects oversized files (413), non-CSV files (400), and duplicates (409).
    """
    ws_id = str(workspace_id)

    # ── 0. Verify workspace membership ───────────────────────────────────
    try:
        ws_check = (
            rls_client(current_user.jwt)
            .table("workspaces")
            .select("id")
            .eq("id", ws_id)
            .execute()
        )
    except Exception as exc:
        logger.error("workspace check failed ws=%s err=%s", ws_id, exc)
        raise HTTPException(status_code=500, detail="Workspace lookup failed.") from exc

    if not ws_check.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found or you are not a member.",
        )

    # ── 1. Validate (extension, size) ────────────────────────────────────
    raw = await validate_csv_upload(file)
    filename = file.filename or "upload.csv"

    # ── 2. Parse CSV ─────────────────────────────────────────────────────
    df = parse_csv(raw)
    row_count = len(df)

    # ── 3. Content hash for deduplication ────────────────────────────────
    content_hash = hashlib.sha256(raw).hexdigest()

    # ── 4. Duplicate check ───────────────────────────────────────────────
    dup_check = (
        service_client()
        .table("files")
        .select("id")
        .eq("workspace_id", ws_id)
        .eq("content_hash", content_hash)
        .execute()
    )
    if dup_check.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This file has already been uploaded to this workspace "
                   f"(content hash: {content_hash[:12]}...).",
        )

    # ── 5. Upload to Supabase Storage ────────────────────────────────────
    try:
        storage_path = upload_file(ws_id, content_hash, filename, raw)
    except Exception as exc:
        logger.error("storage upload failed ws=%s err=%s", ws_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload file to storage.",
        ) from exc

    # ── 6. Insert files row as READY ─────────────────────────────────────
    try:
        result = (
            service_client()
            .table("files")
            .insert({
                "workspace_id": ws_id,
                "filename": filename,
                "storage_path": storage_path,
                "content_hash": content_hash,
                "size_bytes": len(raw),
                "row_count": row_count,
                "state": "READY",
                "uploaded_by": current_user.user_id,
            })
            .execute()
        )
    except Exception as exc:
        logger.error("files insert failed ws=%s err=%s", ws_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save file record.",
        ) from exc

    if not result.data:
        raise HTTPException(status_code=500, detail="File insert returned no data.")

    file_row = result.data[0]
    file_id = file_row["id"]
    logger.info(
        "file uploaded id=%s ws=%s name=%s rows=%d",
        file_id, ws_id, filename, row_count,
    )

    # ── 7. Schema inference + catalog write (L2.2) ───────────────────────
    try:
        columns = infer_schema(df)
        # Derive a logical table name from the filename (strip .csv)
        table_name = filename.rsplit(".", 1)[0] if "." in filename else filename
        create_catalog_entry(
            workspace_id=ws_id,
            file_id=file_id,
            table_name=table_name,
            row_count=row_count,
            columns=columns,
        )
    except Exception as exc:
        # Catalog failure shouldn't fail the upload — file is already READY.
        # Log the error but still return the file record.
        logger.error("catalog write failed file=%s err=%s", file_id, exc)

    return file_row


@router.get(
    "/workspaces/{workspace_id}/files/{file_id}",
    response_model=FileOut,
)
async def get_file(
    workspace_id: UUID,
    file_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_user)],
):
    """Get metadata for a single file (RLS-enforced)."""
    result = (
        rls_client(current_user.jwt)
        .table("files")
        .select("*")
        .eq("id", str(file_id))
        .eq("workspace_id", str(workspace_id))
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found.",
        )
    return result.data[0]


@router.get(
    "/workspaces/{workspace_id}/files",
    response_model=list[FileOut],
)
async def list_files(
    workspace_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_user)],
):
    """List all files in a workspace (RLS-enforced)."""
    result = (
        rls_client(current_user.jwt)
        .table("files")
        .select("*")
        .eq("workspace_id", str(workspace_id))
        .order("created_at", desc=True)
        .execute()
    )
    return result.data
