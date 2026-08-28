"""
Query pipeline orchestrator — the L4–L6 sequence.

Implemented in ticket L5.4 (Session 5), repair loop in L6.1.

Sequence (executed in this order — do not reorder):
  1. Validate IR (ir.validator)          ← raises IRValidationError on bad output
  2. Safety check (execution.safety_validator) ← raises SQLSafetyError
  3. Execute via DuckDB (execution.duckdb_backend)
  4. On ExecutionError: one repair attempt (query_pipeline.repair)
  5. Write query_history + llm_usage rows
  6. Return answer

If step 1 or 2 fails → surface the error, do NOT execute.
If step 4 second attempt fails → surface failure with attempted SQL.
"""
# TODO L5.4: implement run_query(question, workspace_id, user_id, jwt) -> QueryResult
