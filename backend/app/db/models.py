"""
Pydantic models mirroring db/schema-lean.sql.

These are used throughout the backend for serialisation/deserialisation.
Each model corresponds to one table in the lean schema.  Keep field names
and types in sync with the SQL DDL — if the schema changes, update here.
"""
from __future__ import annotations

import enum
from typing import Any, Optional
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Enums (mirror PostgreSQL enum types)
# ---------------------------------------------------------------------------

class WorkspaceRole(str, enum.Enum):
    owner = "owner"
    member = "member"


class FileState(str, enum.Enum):
    UPLOADING = "UPLOADING"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class QueryStatus(str, enum.Enum):
    answered = "answered"
    failed = "failed"


# ---------------------------------------------------------------------------
# Table models
# ---------------------------------------------------------------------------

class User(BaseModel):
    id: UUID
    email: str
    name: Optional[str] = None
    created_at: datetime


class UserApiKeys(BaseModel):
    """Per-user Groq API key storage (encrypted at rest).

    groq_api_key_encrypted is NEVER exposed through the API — the backend
    decrypts it in memory only when making a Groq call. Endpoints return
    only {configured: true/false, model: str | None}.
    """
    user_id: UUID
    # Raw encrypted bytes — not surfaced in API responses.
    groq_api_key_encrypted: bytes
    groq_model: Optional[str] = None
    updated_at: datetime


class Workspace(BaseModel):
    id: UUID
    name: str
    created_by: UUID
    created_at: datetime


class WorkspaceMember(BaseModel):
    workspace_id: UUID
    user_id: UUID
    role: WorkspaceRole
    joined_at: datetime


class File(BaseModel):
    id: UUID
    workspace_id: UUID
    filename: str
    storage_path: str
    content_hash: str
    size_bytes: int
    row_count: Optional[int] = None
    state: FileState
    error_message: Optional[str] = None
    uploaded_by: UUID
    created_at: datetime


class CatalogTable(BaseModel):
    id: UUID
    workspace_id: UUID
    file_id: UUID
    name: str
    row_count: Optional[int] = None
    created_at: datetime


class CatalogColumn(BaseModel):
    id: UUID
    workspace_id: UUID
    table_id: UUID
    name: str
    data_type: str
    nullable: bool = True
    sample_values: Optional[list[Any]] = None


class QueryHistory(BaseModel):
    request_id: UUID
    workspace_id: UUID
    user_id: UUID
    question: str
    status: QueryStatus
    query_ir: Optional[dict[str, Any]] = None
    generated_sql: Optional[str] = None
    result_columns: Optional[list[Any]] = None
    result_rows: Optional[list[Any]] = None
    error_message: Optional[str] = None
    created_at: datetime


class LLMUsage(BaseModel):
    id: UUID
    request_id: Optional[UUID] = None
    workspace_id: UUID
    user_id: UUID  # whose key was used — NOT NULL in schema
    provider: str
    model: str
    purpose: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    estimated_cost_usd: Optional[float] = None
    created_at: datetime
