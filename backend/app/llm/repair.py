"""
Query repair — L6.1 (Session 6).

On DuckDB execution error, sends the error + original IR back to the LLM
for one repair attempt (capped by settings.max_query_repair_attempts).

If the repair succeeds, returns the fixed IR. If it fails, raises with
both the original and repair error for a clear user-facing message.
"""
from __future__ import annotations

import json
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.execution.duckdb_backend import compile_ir, execute_query, ComplexityCapError
from app.execution.safety_validator import SQLSafetyError
from app.ir.validator import validate_ir, IRValidationError
from app.llm.adapters.groq_adapter import GroqAdapter
from app.llm.provider_interface import LLMProviderError, LLMValidationError

logger = get_logger(__name__)

# JSON Schema for the repair response — same as planner output
# (imported lazily to avoid circular dependency issues).
_REPAIR_SCHEMA: dict[str, Any] | None = None


def _get_repair_schema() -> dict[str, Any]:
    global _REPAIR_SCHEMA
    if _REPAIR_SCHEMA is None:
        import json as _json
        from pathlib import Path
        schema_path = Path(__file__).parent / "schemas" / "query_planning_output.schema.json"
        with open(schema_path, "r", encoding="utf-8") as f:
            _REPAIR_SCHEMA = _json.load(f)
    return _REPAIR_SCHEMA


_REPAIR_SYSTEM_PROMPT = """\
You are a SQL query repair assistant. A previous query plan produced an IR \
(intermediate representation) that compiled to SQL, but execution failed with \
an error.

Your job: fix the IR so it produces valid SQL that will execute successfully.

Rules:
1. Output ONLY valid JSON — no markdown, no commentary.
2. Keep ir_version "1.2" and kind "structured".
3. Fix the specific error described below. Common fixes:
   - Wrong column name → use the correct name from the column list.
   - Invalid aggregation on a text column → remove the metric or change column.
   - Missing GROUP BY → add the appropriate group_by columns.
4. Do NOT change the intent of the original query — only fix the error.
5. Set confidence to reflect how sure you are the fix is correct.
"""


def attempt_repair(
    user_id: str,
    original_ir: dict[str, Any],
    original_sql: str,
    error_message: str,
    columns_description: str,
    csv_bytes: bytes,
) -> dict[str, Any]:
    """Attempt to repair a failed query IR via one LLM call.

    Args:
        user_id: UUID of the calling user (for BYOK key lookup).
        original_ir: The IR that failed.
        original_sql: The compiled SQL that failed.
        error_message: The DuckDB error message.
        columns_description: Column metadata for context.
        csv_bytes: The CSV data (for re-execution after repair).

    Returns:
        A dict with ``{"columns": ..., "rows": ..., "sql": ..., "ir": ...,
        "repaired": True}`` on successful repair.

    Raises:
        QueryRepairFailed: if the repair attempt also fails.
    """
    max_attempts = settings.max_query_repair_attempts

    logger.info(
        "Attempting query repair (max %d attempt(s)): error=%s",
        max_attempts, error_message[:200],
    )

    user_message = (
        f"Original IR:\n```json\n{json.dumps(original_ir, indent=2)}\n```\n\n"
        f"Compiled SQL:\n```sql\n{original_sql}\n```\n\n"
        f"Execution error:\n```\n{error_message}\n```\n\n"
        f"Available columns: {columns_description}\n\n"
        f"Fix the IR to resolve this error."
    )

    messages = [
        {"role": "system", "content": _REPAIR_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    adapter = GroqAdapter()

    last_error = error_message
    for attempt in range(1, max_attempts + 1):
        logger.info("Repair attempt %d/%d", attempt, max_attempts)

        try:
            repaired_ir = adapter.generate(
                user_id=user_id,
                purpose="query_repair",
                messages=messages,
                output_schema=_get_repair_schema(),
            )
        except (LLMProviderError, LLMValidationError) as exc:
            last_error = f"Repair LLM call failed: {exc}"
            logger.warning("Repair LLM call failed on attempt %d: %s", attempt, exc)
            continue

        # Validate the repaired IR (strip confidence — it's a planner
        # field, not part of the query IR schema).
        ir_for_validation = {k: v for k, v in repaired_ir.items() if k != "confidence"}
        try:
            validate_ir(ir_for_validation)
        except IRValidationError as exc:
            last_error = f"Repaired IR failed validation: {exc}"
            logger.warning("Repaired IR invalid on attempt %d: %s", attempt, exc)
            continue

        # Compile and execute
        repaired_sql = compile_ir(repaired_ir)

        try:
            result = execute_query(repaired_sql, csv_bytes)
        except (SQLSafetyError, ComplexityCapError, Exception) as exc:
            last_error = f"Repaired query still failed: {exc}"
            logger.warning("Repaired query failed on attempt %d: %s", attempt, exc)
            continue

        # Success!
        logger.info("Repair succeeded on attempt %d", attempt)
        return {
            "columns": result["columns"],
            "rows": result["rows"],
            "sql": repaired_sql,
            "ir": repaired_ir,
            "confidence": repaired_ir.get("confidence", 0.0),
            "repaired": True,
        }

    # All attempts exhausted
    raise QueryRepairFailed(
        original_sql=original_sql,
        original_error=error_message,
        repair_error=last_error,
    )


class QueryRepairFailed(Exception):
    """Raised when all repair attempts fail."""

    def __init__(self, original_sql: str, original_error: str, repair_error: str):
        self.original_sql = original_sql
        self.original_error = original_error
        self.repair_error = repair_error
        super().__init__(
            f"Query failed and repair attempt also failed.\n"
            f"Original error: {original_error}\n"
            f"Repair error: {repair_error}"
        )
