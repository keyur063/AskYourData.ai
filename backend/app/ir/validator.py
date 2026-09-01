"""
IR validator — validates LLM planner output against schemas/query-ir.schema.json.

Implemented in ticket L4.1 (Session 4).

For lean scope: validates structured kind only (no joins array, no raw_sql).
The schema itself (schemas/query-ir.schema.json) is never modified — we're
just not exercising its full surface yet.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

# ---------------------------------------------------------------------------
# Schema loading (once, at import time)
# ---------------------------------------------------------------------------

_SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schemas" / "query-ir.schema.json"

with open(_SCHEMA_PATH, "r", encoding="utf-8") as _f:
    _IR_SCHEMA: dict[str, Any] = json.load(_f)

# Extract sub-definition schemas for per-kind validation.
# The top-level schema uses allOf + if/then with additionalProperties: false
# in each definition, which causes a known draft-07 incompatibility when
# validated monolithically (top-level props like ir_version/kind get rejected
# as "additional" by the sub-definition).  We work around this by validating
# the top-level envelope manually and then validating kind-specific content
# against the appropriate definition schema separately.
_DEFINITIONS = _IR_SCHEMA.get("definitions", {})
_VALID_KINDS = {"structured", "needs_clarification", "raw_sql"}
_KIND_TO_DEFINITION: dict[str, str] = {
    "structured": "structuredQuery",
    "needs_clarification": "clarificationRequest",
    "raw_sql": "rawSqlQuery",
}

# Top-level properties that are envelope-only (not part of any kind definition)
_ENVELOPE_KEYS = {"ir_version", "kind", "request_id"}


class IRValidationError(Exception):
    """Raised when the IR dict doesn't pass JSON Schema validation."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_ir(ir_dict: dict[str, Any]) -> None:
    """Validate an IR dict against schemas/query-ir.schema.json.

    For lean scope this additionally enforces:
      - ``kind`` must be ``"structured"`` (no ``needs_clarification``
        or ``raw_sql`` — those are full-spec features).
      - ``joins`` array must be absent or empty (single-table only).

    Raises:
        IRValidationError: on any validation failure, with a human-readable
            message suitable for logging or returning to the caller.
    """
    # -- Basic type guard --
    if not isinstance(ir_dict, dict):
        raise IRValidationError(
            f"IR must be a JSON object (dict), got {type(ir_dict).__name__}."
        )

    # -- Stage 1: top-level envelope validation ----------------------------

    # ir_version is required and must be "1.2"
    ir_version = ir_dict.get("ir_version")
    if ir_version is None:
        raise IRValidationError("Missing required top-level property: 'ir_version'.")
    if ir_version != "1.2":
        raise IRValidationError(
            f"Unsupported ir_version '{ir_version}' — only '1.2' is supported."
        )

    # kind is required and must be one of the valid enum values
    kind = ir_dict.get("kind")
    if kind is None:
        raise IRValidationError("Missing required top-level property: 'kind'.")
    if kind not in _VALID_KINDS:
        raise IRValidationError(
            f"Invalid kind '{kind}' — must be one of: {sorted(_VALID_KINDS)}."
        )

    # -- Lean-scope guard: only structured kind is supported ---------------
    if kind != "structured":
        raise IRValidationError(
            f"Lean scope only supports kind='structured', got kind='{kind}'. "
            "needs_clarification and raw_sql are deferred to the full spec."
        )

    # -- Stage 2: kind-specific body validation ----------------------------
    # Build a dict with only the non-envelope keys so additionalProperties
    # in the definition schema works correctly.
    body = {k: v for k, v in ir_dict.items() if k not in _ENVELOPE_KEYS}

    definition_name = _KIND_TO_DEFINITION[kind]
    definition_schema = _DEFINITIONS[definition_name]

    # Build a self-contained sub-schema: copy the definitions block into
    # the kind-specific schema so that $ref pointers like
    # "#/definitions/join" resolve correctly against this sub-schema.
    self_contained = {**definition_schema, "definitions": _DEFINITIONS}
    validator = jsonschema.Draft7Validator(self_contained)

    errors = list(validator.iter_errors(body))
    if errors:
        messages = []
        for err in sorted(errors, key=lambda e: list(e.absolute_path)):
            path = ".".join(str(p) for p in err.absolute_path) or "(root)"
            messages.append(f"  [{path}] {err.message}")
        raise IRValidationError(
            "IR failed JSON Schema validation:\n" + "\n".join(messages)
        )

    # -- Lean-scope guard: no joins ----------------------------------------
    joins = ir_dict.get("joins")
    if joins:
        raise IRValidationError(
            f"Lean scope supports single-table queries only — "
            f"received {len(joins)} join(s). Multi-table queries are "
            "deferred to the full spec."
        )
