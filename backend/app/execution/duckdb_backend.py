"""
DuckDB execution backend — compiles validated IR to SQL, executes it.

Implemented in ticket L4.3 (Session 4).

Flow (must follow this order every call):
  1. safety_validator.validate_sql_safety(sql)  ← NEVER skip
  2. complexity caps check (rows scanned, timeout) ← L4.4
  3. duckdb.execute(sql) against the in-memory CSV view
  4. Return results as {"columns": [...], "rows": [...]}

Single-table only for lean scope; no joins.
"""
from __future__ import annotations

import io
from typing import Any

import duckdb

from app.execution.safety_validator import validate_sql_safety


# ---------------------------------------------------------------------------
# IR → SQL compilation
# ---------------------------------------------------------------------------

def _quote(identifier: str) -> str:
    """Double-quote a SQL identifier, escaping embedded double-quotes."""
    return '"' + identifier.replace('"', '""') + '"'


def _compile_metric(metric: dict[str, Any]) -> str:
    """Compile a single metric dict to a SQL expression.

    Examples:
        {"column": "revenue", "aggregation": "SUM"}          → SUM("revenue")
        {"column": "id", "aggregation": "COUNT_DISTINCT"}     → COUNT(DISTINCT "id")
        {"column": "x", "aggregation": "AVG", "alias": "avg"} → AVG("x") AS "avg"
    """
    col = _quote(metric["column"])
    agg = metric["aggregation"]
    if agg == "COUNT_DISTINCT":
        expr = f"COUNT(DISTINCT {col})"
    else:
        expr = f"{agg}({col})"
    alias = metric.get("alias")
    if alias:
        expr += f" AS {_quote(alias)}"
    return expr


def _compile_filter(f: dict[str, Any]) -> str:
    """Compile a single filter dict to a SQL WHERE clause fragment."""
    col = _quote(f["column"])
    op = f["operator"]
    val = f.get("value")

    if op in ("IS NULL", "IS NOT NULL"):
        return f"{col} {op}"

    if op == "BETWEEN":
        if not isinstance(val, list) or len(val) != 2:
            raise ValueError(f"BETWEEN filter requires a 2-element list, got {val!r}")
        return f"{col} BETWEEN {_literal(val[0])} AND {_literal(val[1])}"

    if op in ("IN", "NOT IN"):
        if not isinstance(val, list):
            raise ValueError(f"{op} filter requires a list, got {val!r}")
        items = ", ".join(_literal(v) for v in val)
        return f"{col} {op} ({items})"

    return f"{col} {op} {_literal(val)}"


def _literal(value: Any) -> str:
    """Convert a Python value to a SQL literal.

    Strings are single-quoted (with internal quotes escaped).
    Numbers pass through as-is.  None becomes NULL.
    """
    if value is None:
        return "NULL"
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def compile_ir(ir: dict[str, Any]) -> str:
    """Compile a validated structured IR dict into DuckDB SQL.

    Assumes ir has already been validated by ir.validator.validate_ir().
    The source table name from the IR is mapped to a DuckDB view/table
    named ``"data"`` at execution time (see execute_query), so this
    compiler emits ``FROM "data"`` regardless of the IR source name.

    Returns a SELECT statement string.
    """
    parts: list[str] = []

    # --- SELECT clause ---------------------------------------------------
    select_exprs: list[str] = []

    metrics = ir.get("metrics", [])
    dimensions = ir.get("dimensions", [])
    group_by = ir.get("group_by", [])

    if metrics:
        select_exprs.extend(_compile_metric(m) for m in metrics)
    if dimensions:
        select_exprs.extend(_quote(d) for d in dimensions)

    # Auto-include group_by columns in SELECT when they aren't already
    # covered by dimensions — SQL requires grouped columns to appear
    # in SELECT, and it's what users expect in results.
    dims_set = set(dimensions)
    for g in group_by:
        if g not in dims_set:
            select_exprs.append(_quote(g))

    # If nothing explicit was requested, select everything (preview/lookup
    # without explicit dimensions).
    if not select_exprs:
        select_exprs.append("*")

    parts.append("SELECT " + ", ".join(select_exprs))

    # --- FROM clause (always "data" — the ephemeral table name) ----------
    parts.append('FROM "data"')

    # --- WHERE clause ----------------------------------------------------
    filters = ir.get("filters", [])
    if filters:
        where_clauses = [_compile_filter(f) for f in filters]
        parts.append("WHERE " + " AND ".join(where_clauses))

    # --- GROUP BY --------------------------------------------------------
    if group_by:
        parts.append("GROUP BY " + ", ".join(_quote(g) for g in group_by))

    # --- ORDER BY --------------------------------------------------------
    order_by = ir.get("order_by", [])
    if order_by:
        clauses = [f"{_quote(o['column'])} {o['direction']}" for o in order_by]
        parts.append("ORDER BY " + ", ".join(clauses))

    # --- LIMIT -----------------------------------------------------------
    limit = ir.get("limit")
    if limit is not None:
        parts.append(f"LIMIT {int(limit)}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def execute_query(sql: str, csv_bytes: bytes) -> dict[str, Any]:
    """Execute a compiled SQL query against CSV data using DuckDB.

    1. Runs safety_validator.validate_sql_safety(sql) — NEVER skip.
    2. Creates an in-memory DuckDB connection, loads the CSV into a
       table named ``"data"``.
    3. Executes the SQL.
    4. Returns ``{"columns": [...], "rows": [...]}``.

    Args:
        sql: A SQL string (output of compile_ir).
        csv_bytes: Raw CSV file bytes (same bytes stored in Supabase Storage).

    Returns:
        Dict with ``columns`` (list of column name strings) and ``rows``
        (list of row lists).

    Raises:
        SQLSafetyError: if the SQL fails the safety check.
        duckdb.Error: on DuckDB execution failures.
    """
    import tempfile
    import os

    # --- Step 1: safety check (NON-NEGOTIABLE) ---------------------------
    validate_sql_safety(sql)

    # --- Step 2: load CSV into in-memory DuckDB --------------------------
    # Write CSV bytes to a temp file — DuckDB's read_csv_auto needs a file
    # path (BytesIO is not supported as a parameter in DuckDB 1.1.x).
    fd, tmp_path = tempfile.mkstemp(suffix=".csv")
    try:
        os.write(fd, csv_bytes)
        os.close(fd)

        con = duckdb.connect(":memory:")
        try:
            con.execute(
                f'CREATE TABLE "data" AS SELECT * FROM read_csv_auto(\'{tmp_path.replace(chr(92), "/")}\')'
            )

            # --- Step 3: execute ------------------------------------------
            result = con.execute(sql)
            columns = [desc[0] for desc in result.description]
            rows = result.fetchall()

            return {
                "columns": columns,
                "rows": [list(row) for row in rows],
            }
        finally:
            con.close()
    finally:
        os.unlink(tmp_path)
