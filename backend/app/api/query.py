"""
Query router — POST /workspaces/{id}/query.

Implemented in tickets L5.4 (Session 5) + L6.1 repair loop (Session 6).

Orchestrates the full pipeline:
  1. Catalog lookup (table + columns for the workspace)
  2. LLM planner (NL → IR)
  3. Confidence check (L5.3 fallback)
  4. IR validation (L4.1)
  5. IR → SQL compilation (L4.3)
  6. Safety validation (L4.2, inside execute_query)
  7. DuckDB execution with caps (L4.4)
  8. On execution error → one repair attempt (L6.1)
  9. Return results + generated SQL
"""
from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

import re

from app.core.logging import get_logger
from app.core.security import CurrentUser, require_user
from app.catalog.service import get_tables, get_table_with_columns
from app.execution.duckdb_backend import compile_ir, execute_query, ComplexityCapError
from app.execution.safety_validator import SQLSafetyError
from app.ingestion.storage import fetch_file
from app.ir.validator import validate_ir, IRValidationError
from app.llm.confidence import check_confidence
from app.llm.planner import plan_query
from app.llm.provider_interface import LLMProviderError, LLMValidationError
from app.llm.repair import attempt_repair, QueryRepairFailed

logger = get_logger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    table_id: str = Field(..., description="Catalog table ID to query against.")


class QueryResponse(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    sql: str
    confidence: float
    ir: dict[str, Any] | None = None
    repaired: bool = False


class FallbackResponse(BaseModel):
    fallback: bool = True
    message: str
    confidence: float


# ---------------------------------------------------------------------------
# Write-intent pre-check — rejects questions that ask for mutations.
#
# The safety validator (L4.2) already blocks write keywords in compiled SQL.
# This layer catches the case where the LLM silently answers a mutation
# question with a SELECT (e.g. "delete all North rows" → returns those rows
# instead of refusing). We reject at the question level so the user gets
# a clear message, not a confusing silent SELECT.
# ---------------------------------------------------------------------------
_WRITE_INTENT_KEYWORDS: frozenset[str] = frozenset({
    "delete", "drop", "insert", "update", "alter", "truncate",
    "remove", "erase", "destroy", "wipe",
})
_WRITE_INTENT_RE = re.compile(
    r"\b(" + "|".join(re.escape(kw) for kw in sorted(_WRITE_INTENT_KEYWORDS)) + r")\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/workspaces/{workspace_id}/query",
    response_model=QueryResponse | FallbackResponse,
)
async def query_workspace(
    workspace_id: UUID,
    body: QueryRequest,
    current_user: Annotated[CurrentUser, Depends(require_user)],
):
    """Execute a natural-language query against a workspace table.

    Full pipeline: write-intent check → planner → IR validation →
    SQL compilation → DuckDB execution.
    """
    ws_id = str(workspace_id)

    # --- Step 0: Write-intent check (question-level) ----------------------
    # Catches mutation requests before the planner runs. The SQL-level
    # safety validator (L4.2) is the hard safety guarantee; this step
    # provides consistent UX — a clear refusal rather than a silent SELECT.
    m = _WRITE_INTENT_RE.search(body.question)
    if m:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"This platform is read-only — '{m.group(0)}' operations are not "
                f"supported. Only questions that read or summarise data are allowed."
            ),
        )

    # --- Step 1: Look up catalog table + columns --------------------------
    table = get_table_with_columns(ws_id, body.table_id, current_user.jwt)
    if table is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Table not found in this workspace.",
        )

    table_name = table["name"]
    columns = table.get("columns", [])

    # Build column description for the planner prompt
    columns_description = ", ".join(
        f"{col['name']} ({col['data_type']})" for col in columns
    )

    # --- Step 2: Plan (NL → IR) -------------------------------------------
    try:
        ir = plan_query(
            user_id=current_user.user_id,
            question=body.question,
            table_name=table_name,
            columns_description=columns_description,
        )
    except LLMProviderError as exc:
        logger.error("Planner failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM service error: {exc}",
        ) from exc
    except LLMValidationError as exc:
        logger.warning("Planner output invalid: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Planner produced invalid output: {exc}",
        ) from exc

    # --- Step 3: Confidence check (L5.3) ----------------------------------
    fallback = check_confidence(ir)
    if fallback is not None:
        return FallbackResponse(**fallback)

    # --- Step 4: Validate IR (L4.1) ---------------------------------------
    # Strip 'confidence' — it's a planner field, not in the IR schema.
    ir_for_validation = {k: v for k, v in ir.items() if k != "confidence"}
    try:
        validate_ir(ir_for_validation)
    except IRValidationError as exc:
        logger.warning("IR validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"IR validation error: {exc}",
        ) from exc

    # --- Step 5: Compile IR → SQL (L4.3) ----------------------------------
    sql = compile_ir(ir)

    # --- Step 6: Fetch CSV from Supabase Storage --------------------------
    file_id = table.get("file_id") or table.get("file_id")
    if not file_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Table has no associated file.",
        )

    # Look up the file's storage_path
    from app.core.supabase_client import rls_client
    file_resp = (
        rls_client(current_user.jwt)
        .table("files")
        .select("storage_path")
        .eq("id", str(file_id))
        .maybe_single()
        .execute()
    )
    if file_resp.data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source file not found.",
        )

    csv_bytes = fetch_file(file_resp.data["storage_path"])

    # --- Step 7: Execute (L4.2 safety + L4.3 DuckDB + L4.4 caps) ---------
    try:
        result = execute_query(sql, csv_bytes)
    except SQLSafetyError as exc:
        logger.error("Safety violation in generated SQL: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Generated SQL failed safety check: {exc}",
        ) from exc
    except ComplexityCapError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        ) from exc
    except Exception as exec_err:
        # --- Step 8: Repair attempt (L6.1) --------------------------------
        logger.warning("Execution failed, attempting repair: %s", exec_err)
        try:
            repaired = attempt_repair(
                user_id=current_user.user_id,
                original_ir=ir,
                original_sql=sql,
                error_message=str(exec_err),
                columns_description=columns_description,
                csv_bytes=csv_bytes,
            )
            return QueryResponse(
                columns=repaired["columns"],
                rows=repaired["rows"],
                sql=repaired["sql"],
                confidence=repaired["confidence"],
                ir=repaired["ir"],
                repaired=True,
            )
        except QueryRepairFailed as repair_err:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Query failed and could not be repaired.\n"
                    f"Original error: {repair_err.original_error}\n"
                    f"Attempted SQL: {repair_err.original_sql}"
                ),
            ) from repair_err

    # --- Step 9: Return results -------------------------------------------
    confidence = ir.get("confidence", 0.0)
    return QueryResponse(
        columns=result["columns"],
        rows=result["rows"],
        sql=sql,
        confidence=confidence,
        ir=ir,
    )

