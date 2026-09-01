"""
Query planner — translates natural-language questions into Query IR.

Implemented in ticket L5.2 (Session 5).

Uses the Groq adapter (L5.1) with the system prompt from
prompts/query_planning_v1.yaml and validates the output against
schemas/query_planning_output.schema.json.

The planner is a thin orchestration layer:
  1. Load prompt template and output schema.
  2. Format the user message with table metadata.
  3. Call LLM via GroqAdapter.generate() with JSON mode + schema validation.
  4. Return the validated IR dict (or raise on failure).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from app.core.logging import get_logger
from app.llm.adapters.groq_adapter import GroqAdapter

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Load prompt template and output schema at import time.
# ---------------------------------------------------------------------------

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_SCHEMAS_DIR = Path(__file__).parent / "schemas"

with open(_PROMPTS_DIR / "query_planning_v1.yaml", "r", encoding="utf-8") as _f:
    _PROMPT_TEMPLATE = yaml.safe_load(_f)

with open(_SCHEMAS_DIR / "query_planning_output.schema.json", "r", encoding="utf-8") as _f:
    _OUTPUT_SCHEMA: dict[str, Any] = json.load(_f)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def plan_query(
    user_id: str,
    question: str,
    table_name: str,
    columns_description: str,
) -> dict[str, Any]:
    """Translate a natural-language question into a Query IR dict.

    Args:
        user_id: UUID of the calling user (for BYOK key lookup).
        question: The user's natural-language question.
        table_name: The logical table name (from the catalog).
        columns_description: A human-readable description of the table's
            columns and their types (e.g. "region (text), quantity (integer),
            price (decimal)").

    Returns:
        A validated IR dict matching query_planning_output.schema.json,
        including a ``confidence`` score.

    Raises:
        HTTPException(402): if the user has no API key configured.
        LLMValidationError: if the LLM output doesn't match the schema.
        LLMProviderError: on Groq API failures.
    """
    # --- Build messages ---------------------------------------------------
    system_prompt = _PROMPT_TEMPLATE["system"]
    user_template = _PROMPT_TEMPLATE["user"]

    user_message = user_template.format(
        table_name=table_name,
        columns_description=columns_description,
        question=question,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    # --- Call LLM ---------------------------------------------------------
    adapter = GroqAdapter()
    ir = adapter.generate(
        user_id=user_id,
        purpose="query_planning",
        messages=messages,
        output_schema=_OUTPUT_SCHEMA,
    )

    logger.info(
        "Planner produced IR: operation=%s source=%s confidence=%.2f user=%s",
        ir.get("operation"), ir.get("source"), ir.get("confidence", 0), user_id,
    )

    return ir
