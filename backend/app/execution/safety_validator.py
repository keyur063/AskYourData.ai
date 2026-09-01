"""
Safety validator — rejects any SQL containing write or DDL keywords.

Implemented in ticket L4.2 (Session 4).

NON-NEGOTIABLE (per Lean-MVP-Scope.md §3): this check must run before
every SQL string is handed to DuckDB. Never skip or comment it out.

Rejected keywords (case-insensitive, even inside comments or strings):
  DROP, DELETE, UPDATE, INSERT, ALTER, TRUNCATE, CREATE, REPLACE, MERGE,
  GRANT, REVOKE, EXECUTE, EXEC, COPY, ATTACH, DETACH, PRAGMA, VACUUM

Only SELECT and WITH are permitted as statement openers.

Defence layers (all three must pass):
  1. Input is a non-empty string.
  2. Whitelist: first keyword must be SELECT or WITH.
  3. Blocklist: no write/DDL keyword appears anywhere (word-boundary match,
     so column names like ``updated_at`` don't false-positive, but ``UPDATE``
     inside comments or string literals still triggers rejection — this is
     intentionally conservative).
  4. Multi-statement rejection: semicolons are not allowed (prevents
     ``SELECT 1; DROP TABLE x``).
"""
from __future__ import annotations

import re


class SQLSafetyError(Exception):
    """Raised when a SQL string contains write or DDL keywords."""


# ---------------------------------------------------------------------------
# Blocklist — every keyword that could mutate data or schema.
# Matched as whole words (\b) so "updated_at" doesn't trigger "UPDATE".
# ---------------------------------------------------------------------------
_BLOCKED_KEYWORDS: frozenset[str] = frozenset({
    "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE",
    "CREATE", "REPLACE", "MERGE", "GRANT", "REVOKE",
    "EXECUTE", "EXEC", "COPY", "ATTACH", "DETACH", "PRAGMA", "VACUUM",
})

# Pre-compiled pattern: match any blocked keyword as a whole word.
# re.IGNORECASE handles mixed-case evasion attempts.
_BLOCKED_RE = re.compile(
    r"\b(" + "|".join(re.escape(kw) for kw in sorted(_BLOCKED_KEYWORDS)) + r")\b",
    re.IGNORECASE,
)

# Whitelist: only these keywords may open a statement.
_ALLOWED_OPENERS: frozenset[str] = frozenset({"SELECT", "WITH"})

# Pre-compiled pattern: extract the first SQL keyword (skipping whitespace
# and leading comments).  We intentionally do NOT strip comments before
# blocklist scanning — we only strip them here to find the opener.
_FIRST_KEYWORD_RE = re.compile(
    r"(?:\s|--[^\n]*\n|/\*.*?\*/)*"  # skip leading whitespace / comments
    r"([A-Za-z_]+)",                  # capture first keyword
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_sql_safety(sql: str) -> None:
    """Validate that a SQL string is read-only and safe to execute.

    Raises:
        SQLSafetyError: if the SQL is empty, starts with a non-SELECT/WITH
            keyword, contains any blocked write/DDL keyword, or contains
            a semicolon (multi-statement).
    """
    # -- Layer 1: type/empty guard -----------------------------------------
    if not isinstance(sql, str) or not sql.strip():
        raise SQLSafetyError("SQL must be a non-empty string.")

    # -- Layer 2: whitelist first keyword ----------------------------------
    m = _FIRST_KEYWORD_RE.match(sql)
    if not m:
        raise SQLSafetyError(
            "Could not determine the opening keyword of the SQL statement."
        )
    opener = m.group(1).upper()
    if opener not in _ALLOWED_OPENERS:
        raise SQLSafetyError(
            f"SQL must start with SELECT or WITH, got '{opener}'."
        )

    # -- Layer 3: blocklist scan -------------------------------------------
    match = _BLOCKED_RE.search(sql)
    if match:
        raise SQLSafetyError(
            f"SQL contains blocked write/DDL keyword: '{match.group(0).upper()}'."
        )

    # -- Layer 4: multi-statement rejection --------------------------------
    if ";" in sql:
        raise SQLSafetyError(
            "SQL must be a single statement — semicolons are not allowed."
        )

