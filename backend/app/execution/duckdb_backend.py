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
# TODO L4.3: implement compile_ir(ir: dict) -> str  (IR -> DuckDB SQL)
# TODO L4.3: implement execute_query(sql: str, csv_path: str) -> dict
