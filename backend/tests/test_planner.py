"""
Tests for app.llm.planner — L5.2 acceptance criteria (offline).

Mock-based tests verifying the planner formats prompts correctly, passes
schema validation, and returns well-structured IR dicts.

The full accept criteria ("10 fixture questions produce correct IR on a
known fixture dataset") requires a real Groq call — that's verified in
the L7.1 manual evaluation pass.
"""
from __future__ import annotations

import json
import os
from unittest.mock import patch, MagicMock

import pytest

# Test encryption key
os.environ.setdefault("ENCRYPTION_KEY", "test")
from cryptography.fernet import Fernet
os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()

from app.core.config import Settings
import app.core.config as config_mod
config_mod.settings = Settings()


# =========================================================================
# Planner prompt + schema tests
# =========================================================================

class TestPlannerPrompt:
    """Verify the prompt template and output schema are well-formed."""

    def test_prompt_template_loads(self):
        from app.llm.planner import _PROMPT_TEMPLATE
        assert "system" in _PROMPT_TEMPLATE
        assert "user" in _PROMPT_TEMPLATE
        assert "{table_name}" in _PROMPT_TEMPLATE["user"]
        assert "{columns_description}" in _PROMPT_TEMPLATE["user"]
        assert "{question}" in _PROMPT_TEMPLATE["user"]

    def test_system_prompt_contains_key_instructions(self):
        from app.llm.planner import _PROMPT_TEMPLATE
        system = _PROMPT_TEMPLATE["system"]
        assert "ir_version" in system
        assert "structured" in system
        assert "confidence" in system
        assert "JSON" in system

    def test_output_schema_loads(self):
        from app.llm.planner import _OUTPUT_SCHEMA
        assert _OUTPUT_SCHEMA["type"] == "object"
        assert "confidence" in _OUTPUT_SCHEMA["required"]
        assert "ir_version" in _OUTPUT_SCHEMA["required"]

    def test_output_schema_validates_good_ir(self):
        """A well-formed planner output must pass schema validation."""
        import jsonschema
        from app.llm.planner import _OUTPUT_SCHEMA

        good_ir = {
            "ir_version": "1.2",
            "kind": "structured",
            "source": "sales",
            "operation": "aggregation",
            "metrics": [{"column": "quantity", "aggregation": "SUM", "alias": "total"}],
            "group_by": ["region"],
            "confidence": 0.95,
        }
        jsonschema.validate(good_ir, _OUTPUT_SCHEMA)

    def test_output_schema_rejects_missing_confidence(self):
        """IR without confidence must fail schema validation."""
        import jsonschema
        from app.llm.planner import _OUTPUT_SCHEMA

        bad_ir = {
            "ir_version": "1.2",
            "kind": "structured",
            "source": "sales",
            "operation": "preview",
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad_ir, _OUTPUT_SCHEMA)


# =========================================================================
# plan_query integration test (mocked LLM)
# =========================================================================

class TestPlanQuery:
    """Test plan_query() with mocked GroqAdapter.generate()."""

    @patch("app.llm.planner.GroqAdapter")
    def test_plan_query_formats_and_returns_ir(self, mock_adapter_cls):
        """plan_query() should format the prompt and return the LLM's IR."""
        mock_adapter = MagicMock()
        mock_adapter_cls.return_value = mock_adapter

        expected_ir = {
            "ir_version": "1.2",
            "kind": "structured",
            "source": "sales",
            "operation": "aggregation",
            "metrics": [{"column": "quantity", "aggregation": "SUM", "alias": "total"}],
            "group_by": ["region"],
            "confidence": 0.9,
        }
        mock_adapter.generate.return_value = expected_ir

        from app.llm.planner import plan_query
        result = plan_query(
            user_id="test-user",
            question="total quantity by region",
            table_name="sales",
            columns_description="region (text), product (text), quantity (integer), price (decimal)",
        )

        assert result == expected_ir
        # Verify generate was called with correct purpose and schema
        call_kwargs = mock_adapter.generate.call_args
        assert call_kwargs.kwargs["purpose"] == "query_planning"
        assert call_kwargs.kwargs["output_schema"] is not None
        # Verify messages contain the table info
        messages = call_kwargs.kwargs["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "sales" in messages[1]["content"]
        assert "quantity" in messages[1]["content"]

    @patch("app.llm.planner.GroqAdapter")
    def test_plan_query_passes_user_id(self, mock_adapter_cls):
        """plan_query() must pass the correct user_id for BYOK."""
        mock_adapter = MagicMock()
        mock_adapter_cls.return_value = mock_adapter
        mock_adapter.generate.return_value = {
            "ir_version": "1.2", "kind": "structured",
            "source": "t", "operation": "preview", "confidence": 0.8,
        }

        from app.llm.planner import plan_query
        plan_query(
            user_id="user-abc-123",
            question="show everything",
            table_name="t",
            columns_description="id (integer)",
        )

        call_kwargs = mock_adapter.generate.call_args.kwargs
        assert call_kwargs["user_id"] == "user-abc-123"


# =========================================================================
# 10 fixture IRs — shape validation (offline, mocked)
# These represent the 10 evaluation questions from L5.2/L7.1.
# =========================================================================

_FIXTURE_IRS = [
    # Q1: "What is the total quantity?"
    {"ir_version": "1.2", "kind": "structured", "source": "sales", "operation": "aggregation",
     "metrics": [{"column": "quantity", "aggregation": "SUM", "alias": "total_quantity"}],
     "confidence": 0.95},
    # Q2: "What is the average price?"
    {"ir_version": "1.2", "kind": "structured", "source": "sales", "operation": "aggregation",
     "metrics": [{"column": "price", "aggregation": "AVG", "alias": "avg_price"}],
     "confidence": 0.95},
    # Q3: "Total quantity by region"
    {"ir_version": "1.2", "kind": "structured", "source": "sales", "operation": "aggregation",
     "metrics": [{"column": "quantity", "aggregation": "SUM", "alias": "total"}],
     "group_by": ["region"], "confidence": 0.9},
    # Q4: "Show rows where region is North"
    {"ir_version": "1.2", "kind": "structured", "source": "sales", "operation": "filter",
     "dimensions": ["region", "product", "quantity", "price"],
     "filters": [{"column": "region", "operator": "=", "value": "North"}],
     "confidence": 0.95},
    # Q5: "Top 3 products by quantity"
    {"ir_version": "1.2", "kind": "structured", "source": "sales", "operation": "aggregation",
     "metrics": [{"column": "quantity", "aggregation": "SUM", "alias": "total"}],
     "group_by": ["product"],
     "order_by": [{"column": "total", "direction": "DESC"}],
     "limit": 3, "confidence": 0.85},
    # Q6: "How many unique products?"
    {"ir_version": "1.2", "kind": "structured", "source": "sales", "operation": "aggregation",
     "metrics": [{"column": "product", "aggregation": "COUNT_DISTINCT", "alias": "unique_products"}],
     "confidence": 0.9},
    # Q7: "Min and max price"
    {"ir_version": "1.2", "kind": "structured", "source": "sales", "operation": "aggregation",
     "metrics": [
         {"column": "price", "aggregation": "MIN", "alias": "min_price"},
         {"column": "price", "aggregation": "MAX", "alias": "max_price"},
     ], "confidence": 0.9},
    # Q8: "Preview first 5 rows"
    {"ir_version": "1.2", "kind": "structured", "source": "sales", "operation": "preview",
     "limit": 5, "confidence": 0.95},
    # Q9: "Products with quantity greater than 10"
    {"ir_version": "1.2", "kind": "structured", "source": "sales", "operation": "filter",
     "dimensions": ["product", "quantity"],
     "filters": [{"column": "quantity", "operator": ">", "value": 10}],
     "confidence": 0.9},
    # Q10: "Count of rows by product sorted alphabetically"
    {"ir_version": "1.2", "kind": "structured", "source": "sales", "operation": "aggregation",
     "metrics": [{"column": "product", "aggregation": "COUNT", "alias": "count"}],
     "group_by": ["product"],
     "order_by": [{"column": "product", "direction": "ASC"}],
     "confidence": 0.85},
]


class TestFixtureIRsPassSchema:
    """All 10 fixture IRs must pass the planner output schema."""

    @pytest.mark.parametrize("ir,idx", [(ir, i) for i, ir in enumerate(_FIXTURE_IRS)])
    def test_fixture_ir_valid(self, ir, idx):
        import jsonschema
        from app.llm.planner import _OUTPUT_SCHEMA
        jsonschema.validate(ir, _OUTPUT_SCHEMA)
