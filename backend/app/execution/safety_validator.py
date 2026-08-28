"""
Safety validator — rejects any SQL containing write or DDL keywords.

Implemented in ticket L4.2 (Session 4).

NON-NEGOTIABLE (per Lean-MVP-Scope.md §3): this check must run before
every SQL string is handed to DuckDB. Never skip or comment it out.

Rejected keywords (case-insensitive, even inside comments or strings):
  DROP, DELETE, UPDATE, INSERT, ALTER, TRUNCATE, CREATE, REPLACE, MERGE,
  GRANT, REVOKE, EXECUTE, EXEC, COPY, ATTACH, DETACH, PRAGMA, VACUUM

Only SELECT and WITH are permitted as statement openers.
"""
# TODO L4.2: implement validate_sql_safety(sql: str) -> None
#   raises SQLSafetyError if any write/DDL keyword is found


class SQLSafetyError(Exception):
    """Raised when a SQL string contains write or DDL keywords."""
