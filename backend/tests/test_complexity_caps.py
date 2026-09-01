"""
Tests for complexity caps (L4.4) in app.execution.duckdb_backend.

Accept: a fixture query designed to exceed the row cap is rejected/capped
before completing.
"""
from __future__ import annotations

import pytest

from app.execution.duckdb_backend import (
    compile_ir,
    execute_query,
    ComplexityCapError,
)


# ---------------------------------------------------------------------------
# Fixture CSV — small dataset for boundary testing
# ---------------------------------------------------------------------------

SMALL_CSV = b"""id,name,value
1,Alice,100
2,Bob,200
3,Charlie,300
4,Diana,400
5,Eve,500
"""


def _make_large_csv(n_rows: int) -> bytes:
    """Generate a CSV with exactly n_rows data rows."""
    header = "id,name,value\n"
    rows = "".join(f"{i},name_{i},{i * 10}\n" for i in range(1, n_rows + 1))
    return (header + rows).encode()


# =========================================================================
# Row-count cap tests
# =========================================================================

class TestRowCountCap:
    """Row-count cap rejects queries on datasets exceeding max_rows."""

    def test_under_cap_passes(self):
        """5 rows with max_rows=10 should succeed."""
        sql = compile_ir({
            "ir_version": "1.2", "kind": "structured",
            "source": "data", "operation": "preview",
        })
        result = execute_query(sql, SMALL_CSV, max_rows=10)
        assert len(result["rows"]) == 5

    def test_exactly_at_cap_passes(self):
        """5 rows with max_rows=5 should succeed (≤, not <)."""
        sql = compile_ir({
            "ir_version": "1.2", "kind": "structured",
            "source": "data", "operation": "preview",
        })
        result = execute_query(sql, SMALL_CSV, max_rows=5)
        assert len(result["rows"]) == 5

    def test_over_cap_rejected(self):
        """5 rows with max_rows=3 must be rejected BEFORE executing."""
        sql = compile_ir({
            "ir_version": "1.2", "kind": "structured",
            "source": "data", "operation": "preview",
        })
        with pytest.raises(ComplexityCapError, match="exceeds the maximum"):
            execute_query(sql, SMALL_CSV, max_rows=3)

    def test_large_dataset_over_cap_rejected(self):
        """100-row CSV with max_rows=50 must be rejected."""
        large_csv = _make_large_csv(100)
        sql = compile_ir({
            "ir_version": "1.2", "kind": "structured",
            "source": "data", "operation": "aggregation",
            "metrics": [{"column": "value", "aggregation": "SUM", "alias": "total"}],
        })
        with pytest.raises(ComplexityCapError, match="100 rows.*maximum of 50"):
            execute_query(sql, large_csv, max_rows=50)

    def test_cap_error_message_includes_counts(self):
        """Error message must include actual and max row counts."""
        sql = compile_ir({
            "ir_version": "1.2", "kind": "structured",
            "source": "data", "operation": "preview",
        })
        with pytest.raises(ComplexityCapError) as exc_info:
            execute_query(sql, SMALL_CSV, max_rows=2)
        msg = str(exc_info.value)
        assert "5" in msg   # actual count
        assert "2" in msg   # cap value


# =========================================================================
# Timeout cap tests
# =========================================================================

class TestTimeoutCap:
    """Timeout cap stops long-running queries."""

    def test_fast_query_within_timeout(self):
        """A trivial query with a generous timeout should succeed."""
        sql = compile_ir({
            "ir_version": "1.2", "kind": "structured",
            "source": "data", "operation": "preview",
        })
        result = execute_query(sql, SMALL_CSV, timeout_seconds=10)
        assert len(result["rows"]) == 5


# =========================================================================
# Verify existing tests still pass with caps (defaults from settings)
# =========================================================================

class TestExistingBehaviorWithCaps:
    """Caps should not break normal queries within limits."""

    def test_aggregation_still_works(self):
        """SUM with a generous row cap and timeout should succeed."""
        csv = _make_large_csv(50)
        sql = compile_ir({
            "ir_version": "1.2", "kind": "structured",
            "source": "data", "operation": "aggregation",
            "metrics": [{"column": "value", "aggregation": "SUM", "alias": "total"}],
        })
        result = execute_query(sql, csv, max_rows=1000, timeout_seconds=10)
        # sum of 10+20+...+500 = 10 * sum(1..50) = 10 * 1275 = 12750
        assert result["rows"][0][0] == 12750

    def test_filter_with_cap(self):
        csv = _make_large_csv(20)
        sql = compile_ir({
            "ir_version": "1.2", "kind": "structured",
            "source": "data", "operation": "filter",
            "dimensions": ["id", "value"],
            "filters": [{"column": "id", "operator": "<=", "value": 5}],
        })
        result = execute_query(sql, csv, max_rows=100, timeout_seconds=10)
        assert len(result["rows"]) == 5
