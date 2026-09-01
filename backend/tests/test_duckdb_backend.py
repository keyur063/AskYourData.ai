"""
Tests for app.execution.duckdb_backend — L4.3 acceptance criteria.

Fixture IRs (aggregation, filter, group_by, order_by, limit) return
correct results on a known fixture CSV.
"""
from __future__ import annotations

import pytest

from app.execution.duckdb_backend import compile_ir, execute_query
from app.execution.safety_validator import SQLSafetyError


# ---------------------------------------------------------------------------
# Fixture CSV — a small sales dataset used across all tests.
# ---------------------------------------------------------------------------

FIXTURE_CSV = b"""region,product,quantity,price,date
North,Widget,10,5.00,2024-01-15
North,Gadget,3,25.00,2024-01-20
South,Widget,7,5.00,2024-02-10
South,Gadget,15,25.00,2024-02-15
East,Widget,20,5.00,2024-03-01
East,Gizmo,2,100.00,2024-03-10
North,Gizmo,1,100.00,2024-03-15
South,Widget,12,5.00,2024-03-20
"""


def _run(ir: dict) -> dict:
    """Shortcut: compile IR → execute against FIXTURE_CSV → return result."""
    sql = compile_ir(ir)
    return execute_query(sql, FIXTURE_CSV)


# =========================================================================
# compile_ir tests — check generated SQL structure
# =========================================================================

class TestCompileIR:
    """Test that compile_ir produces correct DuckDB SQL strings."""

    def test_simple_preview(self):
        sql = compile_ir({
            "ir_version": "1.2", "kind": "structured",
            "source": "sales", "operation": "preview",
            "limit": 5,
        })
        assert 'SELECT *' in sql
        assert 'FROM "data"' in sql
        assert 'LIMIT 5' in sql

    def test_aggregation_with_group_by(self):
        sql = compile_ir({
            "ir_version": "1.2", "kind": "structured",
            "source": "sales", "operation": "aggregation",
            "metrics": [{"column": "quantity", "aggregation": "SUM", "alias": "total_qty"}],
            "group_by": ["region"],
        })
        assert 'SUM("quantity") AS "total_qty"' in sql
        assert 'GROUP BY "region"' in sql

    def test_count_distinct(self):
        sql = compile_ir({
            "ir_version": "1.2", "kind": "structured",
            "source": "sales", "operation": "aggregation",
            "metrics": [{"column": "product", "aggregation": "COUNT_DISTINCT"}],
        })
        assert 'COUNT(DISTINCT "product")' in sql

    def test_filter_equals(self):
        sql = compile_ir({
            "ir_version": "1.2", "kind": "structured",
            "source": "sales", "operation": "filter",
            "dimensions": ["product", "quantity"],
            "filters": [{"column": "region", "operator": "=", "value": "North"}],
        })
        assert "\"region\" = 'North'" in sql

    def test_filter_in(self):
        sql = compile_ir({
            "ir_version": "1.2", "kind": "structured",
            "source": "sales", "operation": "filter",
            "dimensions": ["product"],
            "filters": [{"column": "region", "operator": "IN", "value": ["North", "South"]}],
        })
        assert "\"region\" IN ('North', 'South')" in sql

    def test_filter_between(self):
        sql = compile_ir({
            "ir_version": "1.2", "kind": "structured",
            "source": "sales", "operation": "filter",
            "dimensions": ["product", "quantity"],
            "filters": [{"column": "quantity", "operator": "BETWEEN", "value": [5, 15]}],
        })
        assert '"quantity" BETWEEN 5 AND 15' in sql

    def test_filter_is_null(self):
        sql = compile_ir({
            "ir_version": "1.2", "kind": "structured",
            "source": "sales", "operation": "filter",
            "dimensions": ["product"],
            "filters": [{"column": "region", "operator": "IS NULL", "value": None}],
        })
        assert '"region" IS NULL' in sql

    def test_order_by(self):
        sql = compile_ir({
            "ir_version": "1.2", "kind": "structured",
            "source": "sales", "operation": "preview",
            "dimensions": ["product", "quantity"],
            "order_by": [{"column": "quantity", "direction": "DESC"}],
        })
        assert '"quantity" DESC' in sql

    def test_dimensions_only(self):
        sql = compile_ir({
            "ir_version": "1.2", "kind": "structured",
            "source": "sales", "operation": "lookup",
            "dimensions": ["region", "product"],
        })
        assert '"region", "product"' in sql


# =========================================================================
# execute_query end-to-end tests — correct results on fixture CSV
# =========================================================================

class TestExecuteQuery:
    """End-to-end: compile IR → execute → verify correct results."""

    def test_preview_all_rows(self):
        """Preview with no limit returns all 8 rows."""
        result = _run({
            "ir_version": "1.2", "kind": "structured",
            "source": "sales", "operation": "preview",
        })
        assert result["columns"] == ["region", "product", "quantity", "price", "date"]
        assert len(result["rows"]) == 8

    def test_preview_with_limit(self):
        result = _run({
            "ir_version": "1.2", "kind": "structured",
            "source": "sales", "operation": "preview",
            "limit": 3,
        })
        assert len(result["rows"]) == 3

    def test_aggregation_sum(self):
        """SUM(quantity) should be 70 across all rows."""
        result = _run({
            "ir_version": "1.2", "kind": "structured",
            "source": "sales", "operation": "aggregation",
            "metrics": [{"column": "quantity", "aggregation": "SUM", "alias": "total"}],
        })
        assert result["columns"] == ["total"]
        assert result["rows"][0][0] == 70

    def test_aggregation_with_group_by(self):
        """SUM(quantity) grouped by region."""
        result = _run({
            "ir_version": "1.2", "kind": "structured",
            "source": "sales", "operation": "aggregation",
            "metrics": [{"column": "quantity", "aggregation": "SUM", "alias": "total"}],
            "group_by": ["region"],
            "order_by": [{"column": "region", "direction": "ASC"}],
        })
        assert result["columns"] == ["total", "region"]
        # East: 20+2=22, North: 10+3+1=14, South: 7+15+12=34
        data = {row[1]: row[0] for row in result["rows"]}
        assert data["East"] == 22
        assert data["North"] == 14
        assert data["South"] == 34

    def test_aggregation_count_distinct(self):
        """COUNT(DISTINCT product) should be 3 (Widget, Gadget, Gizmo)."""
        result = _run({
            "ir_version": "1.2", "kind": "structured",
            "source": "sales", "operation": "aggregation",
            "metrics": [{"column": "product", "aggregation": "COUNT_DISTINCT", "alias": "n"}],
        })
        assert result["rows"][0][0] == 3

    def test_aggregation_min_max(self):
        result = _run({
            "ir_version": "1.2", "kind": "structured",
            "source": "sales", "operation": "aggregation",
            "metrics": [
                {"column": "quantity", "aggregation": "MIN", "alias": "min_qty"},
                {"column": "quantity", "aggregation": "MAX", "alias": "max_qty"},
            ],
        })
        assert result["rows"][0][0] == 1   # min
        assert result["rows"][0][1] == 20  # max

    def test_filter_equals(self):
        """Filter region = 'North' should return 3 rows."""
        result = _run({
            "ir_version": "1.2", "kind": "structured",
            "source": "sales", "operation": "filter",
            "dimensions": ["region", "product", "quantity"],
            "filters": [{"column": "region", "operator": "=", "value": "North"}],
        })
        assert len(result["rows"]) == 3
        assert all(row[0] == "North" for row in result["rows"])

    def test_filter_greater_than(self):
        """quantity > 10 should return 3 rows (15, 20, 12)."""
        result = _run({
            "ir_version": "1.2", "kind": "structured",
            "source": "sales", "operation": "filter",
            "dimensions": ["product", "quantity"],
            "filters": [{"column": "quantity", "operator": ">", "value": 10}],
        })
        assert len(result["rows"]) == 3
        assert all(row[1] > 10 for row in result["rows"])

    def test_filter_in(self):
        """product IN ('Widget', 'Gizmo') should return 6 rows."""
        result = _run({
            "ir_version": "1.2", "kind": "structured",
            "source": "sales", "operation": "filter",
            "dimensions": ["product", "quantity"],
            "filters": [{"column": "product", "operator": "IN", "value": ["Widget", "Gizmo"]}],
        })
        assert len(result["rows"]) == 6
        products = {row[0] for row in result["rows"]}
        assert products == {"Widget", "Gizmo"}

    def test_filter_like(self):
        """product LIKE 'Wid%' should return Widget rows (4 of them)."""
        result = _run({
            "ir_version": "1.2", "kind": "structured",
            "source": "sales", "operation": "filter",
            "dimensions": ["product"],
            "filters": [{"column": "product", "operator": "LIKE", "value": "Wid%"}],
        })
        assert len(result["rows"]) == 4
        assert all(row[0] == "Widget" for row in result["rows"])

    def test_order_by_desc_with_limit(self):
        """Top 3 by quantity descending: 20, 15, 12."""
        result = _run({
            "ir_version": "1.2", "kind": "structured",
            "source": "sales", "operation": "preview",
            "dimensions": ["product", "quantity"],
            "order_by": [{"column": "quantity", "direction": "DESC"}],
            "limit": 3,
        })
        quantities = [row[1] for row in result["rows"]]
        assert quantities == [20, 15, 12]

    def test_aggregation_avg(self):
        """AVG(price) should be mean of [5,25,5,25,5,100,100,5] = 33.75."""
        result = _run({
            "ir_version": "1.2", "kind": "structured",
            "source": "sales", "operation": "aggregation",
            "metrics": [{"column": "price", "aggregation": "AVG", "alias": "avg_price"}],
        })
        assert abs(result["rows"][0][0] - 33.75) < 0.01

    def test_combined_filter_group_order_limit(self):
        """Combined: filter + group_by + order + limit in one query."""
        result = _run({
            "ir_version": "1.2", "kind": "structured",
            "source": "sales", "operation": "aggregation",
            "metrics": [{"column": "quantity", "aggregation": "SUM", "alias": "total"}],
            "group_by": ["product"],
            "filters": [{"column": "region", "operator": "!=", "value": "East"}],
            "order_by": [{"column": "total", "direction": "DESC"}],
            "limit": 2,
        })
        # Excluding East: Widget=10+7+12=29, Gadget=3+15=18, Gizmo=1
        # Top 2 desc: Widget(29), Gadget(18)
        assert len(result["rows"]) == 2
        assert result["rows"][0][0] == 29  # Widget total
        assert result["rows"][1][0] == 18  # Gadget total


# =========================================================================
# Safety integration — execute_query MUST call safety validator
# =========================================================================

class TestSafetyIntegration:
    """execute_query must always run the safety validator first."""

    def test_unsafe_sql_rejected(self):
        """Manually passing a DROP statement to execute_query must fail."""
        with pytest.raises(SQLSafetyError, match="DROP"):
            execute_query("DROP TABLE data", FIXTURE_CSV)

    def test_update_rejected(self):
        with pytest.raises(SQLSafetyError):
            execute_query("UPDATE data SET quantity = 0", FIXTURE_CSV)
