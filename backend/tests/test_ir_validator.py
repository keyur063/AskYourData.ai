"""
Tests for app.ir.validator — L4.1 acceptance criteria.

Valid/invalid IR fixtures must pass/fail as expected.
"""
import pytest

from app.ir.validator import validate_ir, IRValidationError


# =========================================================================
# Valid fixtures — these must all pass
# =========================================================================

class TestValidIR:
    """Valid structured IRs that should pass validation."""

    def test_minimal_aggregation(self):
        """Simplest valid structured IR — just source + operation."""
        validate_ir({
            "ir_version": "1.2",
            "kind": "structured",
            "source": "sales",
            "operation": "aggregation",
        })

    def test_aggregation_with_metrics_and_group_by(self):
        validate_ir({
            "ir_version": "1.2",
            "kind": "structured",
            "source": "sales",
            "operation": "aggregation",
            "metrics": [
                {"column": "revenue", "aggregation": "SUM", "alias": "total_revenue"},
            ],
            "group_by": ["region"],
            "order_by": [{"column": "total_revenue", "direction": "DESC"}],
            "limit": 10,
        })

    def test_filter_operation(self):
        validate_ir({
            "ir_version": "1.2",
            "kind": "structured",
            "source": "employees",
            "operation": "filter",
            "dimensions": ["name", "department"],
            "filters": [
                {"column": "department", "operator": "=", "value": "Engineering"},
            ],
        })

    def test_lookup_operation(self):
        validate_ir({
            "ir_version": "1.2",
            "kind": "structured",
            "source": "products",
            "operation": "lookup",
            "dimensions": ["product_name", "price"],
            "filters": [
                {"column": "product_name", "operator": "LIKE", "value": "%widget%"},
            ],
            "limit": 5,
        })

    def test_preview_operation(self):
        validate_ir({
            "ir_version": "1.2",
            "kind": "structured",
            "source": "transactions",
            "operation": "preview",
            "dimensions": ["date", "amount", "category"],
            "limit": 100,
        })

    def test_multiple_filters(self):
        validate_ir({
            "ir_version": "1.2",
            "kind": "structured",
            "source": "orders",
            "operation": "filter",
            "dimensions": ["order_id", "total"],
            "filters": [
                {"column": "total", "operator": ">=", "value": 100},
                {"column": "status", "operator": "IN", "value": ["shipped", "delivered"]},
            ],
        })

    def test_count_distinct_metric(self):
        validate_ir({
            "ir_version": "1.2",
            "kind": "structured",
            "source": "users",
            "operation": "aggregation",
            "metrics": [
                {"column": "user_id", "aggregation": "COUNT_DISTINCT"},
            ],
        })

    def test_empty_joins_array_is_allowed(self):
        """An empty joins array is not a lean-scope violation."""
        validate_ir({
            "ir_version": "1.2",
            "kind": "structured",
            "source": "sales",
            "operation": "aggregation",
            "joins": [],
        })

    def test_with_request_id(self):
        validate_ir({
            "ir_version": "1.2",
            "kind": "structured",
            "request_id": "abc-123",
            "source": "data",
            "operation": "preview",
        })


# =========================================================================
# Invalid fixtures — these must all raise IRValidationError
# =========================================================================

class TestInvalidIR:
    """Invalid or lean-scope-unsupported IRs that must be rejected."""

    # -- Schema-level failures --

    def test_not_a_dict(self):
        with pytest.raises(IRValidationError, match="must be a JSON object"):
            validate_ir("not a dict")  # type: ignore[arg-type]

    def test_missing_ir_version(self):
        with pytest.raises(IRValidationError, match="ir_version"):
            validate_ir({"kind": "structured", "source": "t", "operation": "filter"})

    def test_missing_kind(self):
        with pytest.raises(IRValidationError, match="kind"):
            validate_ir({"ir_version": "1.2", "source": "t", "operation": "filter"})

    def test_wrong_ir_version(self):
        with pytest.raises(IRValidationError):
            validate_ir({
                "ir_version": "2.0",
                "kind": "structured",
                "source": "t",
                "operation": "filter",
            })

    def test_missing_source(self):
        with pytest.raises(IRValidationError, match="source"):
            validate_ir({
                "ir_version": "1.2",
                "kind": "structured",
                "operation": "filter",
            })

    def test_missing_operation(self):
        with pytest.raises(IRValidationError, match="operation"):
            validate_ir({
                "ir_version": "1.2",
                "kind": "structured",
                "source": "t",
            })

    def test_invalid_operation(self):
        with pytest.raises(IRValidationError):
            validate_ir({
                "ir_version": "1.2",
                "kind": "structured",
                "source": "t",
                "operation": "delete_everything",
            })

    def test_invalid_aggregation_function(self):
        with pytest.raises(IRValidationError):
            validate_ir({
                "ir_version": "1.2",
                "kind": "structured",
                "source": "t",
                "operation": "aggregation",
                "metrics": [{"column": "x", "aggregation": "STDDEV"}],
            })

    def test_invalid_filter_operator(self):
        with pytest.raises(IRValidationError):
            validate_ir({
                "ir_version": "1.2",
                "kind": "structured",
                "source": "t",
                "operation": "filter",
                "filters": [{"column": "x", "operator": "CONTAINS", "value": "y"}],
            })

    def test_limit_zero(self):
        with pytest.raises(IRValidationError):
            validate_ir({
                "ir_version": "1.2",
                "kind": "structured",
                "source": "t",
                "operation": "preview",
                "limit": 0,
            })

    def test_additional_properties_rejected(self):
        with pytest.raises(IRValidationError):
            validate_ir({
                "ir_version": "1.2",
                "kind": "structured",
                "source": "t",
                "operation": "filter",
                "sneaky_extra_field": True,
            })

    # -- Lean-scope guards --

    def test_kind_needs_clarification_rejected(self):
        with pytest.raises(IRValidationError, match="Lean scope only supports kind='structured'"):
            validate_ir({
                "ir_version": "1.2",
                "kind": "needs_clarification",
                "reason": "ambiguous_column",
                "options": [
                    {"label": "a", "resolves_to": {}},
                    {"label": "b", "resolves_to": {}},
                ],
            })

    def test_kind_raw_sql_rejected(self):
        with pytest.raises(IRValidationError, match="Lean scope only supports kind='structured'"):
            validate_ir({
                "ir_version": "1.2",
                "kind": "raw_sql",
                "sql": "SELECT 1",
                "source_tables": ["t"],
                "justification": "test",
            })

    def test_joins_rejected(self):
        with pytest.raises(IRValidationError, match="single-table queries only"):
            validate_ir({
                "ir_version": "1.2",
                "kind": "structured",
                "source": "orders",
                "operation": "aggregation",
                "joins": [{
                    "left": "orders",
                    "right": "customers",
                    "left_column": "customer_id",
                    "right_column": "id",
                    "join_type": "inner",
                }],
            })

    def test_empty_dict(self):
        with pytest.raises(IRValidationError):
            validate_ir({})

    def test_none_input(self):
        with pytest.raises(IRValidationError, match="must be a JSON object"):
            validate_ir(None)  # type: ignore[arg-type]
