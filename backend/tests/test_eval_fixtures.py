"""
L7.1 — Automated evaluation: 10 fixture questions against sales.csv.

These tests verify the compiler + executor pipeline end-to-end using the
10 fixture IRs from L5.2. The LLM planning step is bypassed — we pass the
known-correct IRs directly to compile_ir() and execute_query().

This is the offline half of L7.1. The manual half (asking the same
questions through the UI with a real Groq key) is documented in
docs/eval-L7.1.md.

Expected answers are computed from tests/fixtures/sales.csv:
  region,product,quantity,price  (12 rows)
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("ENCRYPTION_KEY", "test")
from cryptography.fernet import Fernet
os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()

from app.execution.duckdb_backend import compile_ir, execute_query

# ---------------------------------------------------------------------------
# Fixture CSV
# ---------------------------------------------------------------------------

_CSV = (Path(__file__).parent / "fixtures" / "sales.csv").read_bytes()

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def run(ir: dict) -> dict:
    """Strip confidence, compile IR, execute against fixture CSV."""
    clean_ir = {k: v for k, v in ir.items() if k != "confidence"}
    sql = compile_ir(clean_ir)
    return execute_query(sql, _CSV)


# ---------------------------------------------------------------------------
# Q1: "What is the total quantity?"
# ---------------------------------------------------------------------------

class TestQ1TotalQuantity:
    def test_result(self):
        ir = {
            "ir_version": "1.2", "kind": "structured", "source": "sales",
            "operation": "aggregation",
            "metrics": [{"column": "quantity", "aggregation": "SUM", "alias": "total_quantity"}],
        }
        r = run(ir)
        assert r["columns"] == ["total_quantity"]
        assert r["rows"] == [[165]]


# ---------------------------------------------------------------------------
# Q2: "What is the average price?"
# ---------------------------------------------------------------------------

class TestQ2AvgPrice:
    def test_result(self):
        ir = {
            "ir_version": "1.2", "kind": "structured", "source": "sales",
            "operation": "aggregation",
            "metrics": [{"column": "price", "aggregation": "AVG", "alias": "avg_price"}],
        }
        r = run(ir)
        assert r["columns"] == ["avg_price"]
        assert abs(r["rows"][0][0] - 9.99) < 0.001


# ---------------------------------------------------------------------------
# Q3: "Total quantity by region"
# ---------------------------------------------------------------------------

class TestQ3TotalByRegion:
    def test_result(self):
        ir = {
            "ir_version": "1.2", "kind": "structured", "source": "sales",
            "operation": "aggregation",
            "metrics": [{"column": "quantity", "aggregation": "SUM", "alias": "total"}],
            "group_by": ["region"],
        }
        r = run(ir)
        assert "region" in r["columns"]
        assert "total" in r["columns"]
        # All 4 regions present, totals sum to 165
        total_col = r["columns"].index("total")
        grand_total = sum(row[total_col] for row in r["rows"])
        assert grand_total == 165
        assert len(r["rows"]) == 4  # North, South, East, West


# ---------------------------------------------------------------------------
# Q4: "Show rows where region is North"
# ---------------------------------------------------------------------------

class TestQ4FilterNorth:
    def test_result(self):
        ir = {
            "ir_version": "1.2", "kind": "structured", "source": "sales",
            "operation": "filter",
            "dimensions": ["region", "product", "quantity", "price"],
            "filters": [{"column": "region", "operator": "=", "value": "North"}],
        }
        r = run(ir)
        assert "region" in r["columns"]
        assert len(r["rows"]) == 4  # 4 North rows in fixture
        region_col = r["columns"].index("region")
        assert all(row[region_col] == "North" for row in r["rows"])


# ---------------------------------------------------------------------------
# Q5: "Top 3 products by quantity"
# ---------------------------------------------------------------------------

class TestQ5Top3Products:
    def test_result(self):
        ir = {
            "ir_version": "1.2", "kind": "structured", "source": "sales",
            "operation": "aggregation",
            "metrics": [{"column": "quantity", "aggregation": "SUM", "alias": "total"}],
            "group_by": ["product"],
            "order_by": [{"column": "total", "direction": "DESC"}],
            "limit": 3,
        }
        r = run(ir)
        assert len(r["rows"]) == 3
        total_col = r["columns"].index("total")
        product_col = r["columns"].index("product")
        # Top product by quantity is Widget C (64)
        assert r["rows"][0][product_col] == "Widget C"
        assert r["rows"][0][total_col] == 64
        # Second is Widget B (62)
        assert r["rows"][1][product_col] == "Widget B"
        assert r["rows"][1][total_col] == 62


# ---------------------------------------------------------------------------
# Q6: "How many unique products?"
# ---------------------------------------------------------------------------

class TestQ6UniqueProducts:
    def test_result(self):
        ir = {
            "ir_version": "1.2", "kind": "structured", "source": "sales",
            "operation": "aggregation",
            "metrics": [{"column": "product", "aggregation": "COUNT_DISTINCT", "alias": "unique_products"}],
        }
        r = run(ir)
        assert r["columns"] == ["unique_products"]
        assert r["rows"] == [[3]]  # Widget A, B, C


# ---------------------------------------------------------------------------
# Q7: "Min and max price"
# ---------------------------------------------------------------------------

class TestQ7MinMaxPrice:
    def test_result(self):
        ir = {
            "ir_version": "1.2", "kind": "structured", "source": "sales",
            "operation": "aggregation",
            "metrics": [
                {"column": "price", "aggregation": "MIN", "alias": "min_price"},
                {"column": "price", "aggregation": "MAX", "alias": "max_price"},
            ],
        }
        r = run(ir)
        assert set(r["columns"]) == {"min_price", "max_price"}
        min_col = r["columns"].index("min_price")
        max_col = r["columns"].index("max_price")
        assert abs(r["rows"][0][min_col] - 4.99) < 0.001
        assert abs(r["rows"][0][max_col] - 14.99) < 0.001


# ---------------------------------------------------------------------------
# Q8: "Preview first 5 rows"
# ---------------------------------------------------------------------------

class TestQ8Preview:
    def test_result(self):
        ir = {
            "ir_version": "1.2", "kind": "structured", "source": "sales",
            "operation": "preview",
            "limit": 5,
        }
        r = run(ir)
        assert len(r["rows"]) == 5
        # All 4 columns present in preview
        for col in ["region", "product", "quantity", "price"]:
            assert col in r["columns"]


# ---------------------------------------------------------------------------
# Q9: "Products with quantity greater than 10"
# ---------------------------------------------------------------------------

class TestQ9QuantityGt10:
    def test_result(self):
        ir = {
            "ir_version": "1.2", "kind": "structured", "source": "sales",
            "operation": "filter",
            "dimensions": ["product", "quantity"],
            "filters": [{"column": "quantity", "operator": ">", "value": 10}],
        }
        r = run(ir)
        assert "quantity" in r["columns"]
        qty_col = r["columns"].index("quantity")
        # 8 rows have quantity > 10 in the fixture
        assert len(r["rows"]) == 8
        assert all(row[qty_col] > 10 for row in r["rows"])


# ---------------------------------------------------------------------------
# Q10: "Count of rows by product sorted alphabetically"
# ---------------------------------------------------------------------------

class TestQ10CountByProduct:
    def test_result(self):
        ir = {
            "ir_version": "1.2", "kind": "structured", "source": "sales",
            "operation": "aggregation",
            "metrics": [{"column": "product", "aggregation": "COUNT", "alias": "count"}],
            "group_by": ["product"],
            "order_by": [{"column": "product", "direction": "ASC"}],
        }
        r = run(ir)
        product_col = r["columns"].index("product")
        count_col = r["columns"].index("count")
        products = [row[product_col] for row in r["rows"]]
        counts = [row[count_col] for row in r["rows"]]
        # Alphabetical order: A, B, C
        assert products == ["Widget A", "Widget B", "Widget C"]
        # 4 rows each in the fixture
        assert counts == [4, 4, 4]
