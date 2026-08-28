"""
IR validator — validates LLM planner output against schemas/query-ir.schema.json.

Implemented in ticket L4.1 (Session 4).

For lean scope: validates structured kind only (no joins array, no raw_sql).
The schema itself (schemas/query-ir.schema.json) is never modified — we're
just not exercising its full surface yet.
"""
# TODO L4.1: implement validate_ir(ir_dict) -> None (raises IRValidationError on failure)
# Load schema from: Path(__file__).parents[4] / "schemas" / "query-ir.schema.json"


class IRValidationError(Exception):
    """Raised when the IR dict doesn't pass JSON Schema validation."""
