"""
Tests for app.llm.repair — L6.1 acceptance criteria (offline, mocked).

Accept: a fixture with a fixable error (bad column name) self-corrects;
an unfixable fixture fails gracefully with a clear message.
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

from app.llm.repair import attempt_repair, QueryRepairFailed

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_ORIGINAL_IR = {
    "ir_version": "1.2",
    "kind": "structured",
    "source": "sales",
    "operation": "aggregation",
    "metrics": [{"column": "revenu", "aggregation": "SUM", "alias": "total"}],
    "confidence": 0.9,
}

_ORIGINAL_SQL = 'SELECT SUM("revenu") AS "total"\nFROM "data"'

_FIXED_IR = {
    "ir_version": "1.2",
    "kind": "structured",
    "source": "sales",
    "operation": "aggregation",
    "metrics": [{"column": "revenue", "aggregation": "SUM", "alias": "total"}],
    "confidence": 0.85,
}

_CSV_BYTES = b"id,name,revenue\n1,Alice,100\n2,Bob,200\n"

_COLUMNS_DESC = "id (integer), name (text), revenue (decimal)"


# =========================================================================
# Fixable error — self-corrects
# =========================================================================

class TestFixableRepair:
    """A fixable error (bad column name) should self-correct."""

    @patch("app.llm.repair.GroqAdapter")
    def test_bad_column_name_repaired(self, mock_adapter_cls):
        """Repair fixes a typo in the column name."""
        mock_adapter = MagicMock()
        mock_adapter_cls.return_value = mock_adapter
        mock_adapter.generate.return_value = _FIXED_IR

        result = attempt_repair(
            user_id="test-user",
            original_ir=_ORIGINAL_IR,
            original_sql=_ORIGINAL_SQL,
            error_message='Binder Error: column "revenu" not found',
            columns_description=_COLUMNS_DESC,
            csv_bytes=_CSV_BYTES,
        )

        assert result["repaired"] is True
        assert result["columns"] == ["total"]
        assert result["rows"][0][0] == 300  # 100 + 200
        assert "revenue" in result["sql"]  # fixed column name

    @patch("app.llm.repair.GroqAdapter")
    def test_repair_passes_error_to_llm(self, mock_adapter_cls):
        """The error message and original IR should be passed to the LLM."""
        mock_adapter = MagicMock()
        mock_adapter_cls.return_value = mock_adapter
        mock_adapter.generate.return_value = _FIXED_IR

        attempt_repair(
            user_id="test-user",
            original_ir=_ORIGINAL_IR,
            original_sql=_ORIGINAL_SQL,
            error_message='column "revenu" not found',
            columns_description=_COLUMNS_DESC,
            csv_bytes=_CSV_BYTES,
        )

        call_kwargs = mock_adapter.generate.call_args.kwargs
        assert call_kwargs["purpose"] == "query_repair"
        user_msg = call_kwargs["messages"][1]["content"]
        assert "revenu" in user_msg  # original error
        assert "revenue" in user_msg  # available columns


# =========================================================================
# Unfixable error — fails gracefully
# =========================================================================

class TestUnfixableRepair:
    """An unfixable error should fail gracefully with a clear message."""

    @patch("app.llm.repair.GroqAdapter")
    def test_unfixable_raises_repair_failed(self, mock_adapter_cls):
        """If the LLM can't fix it, QueryRepairFailed is raised."""
        from app.llm.provider_interface import LLMProviderError

        mock_adapter = MagicMock()
        mock_adapter_cls.return_value = mock_adapter
        mock_adapter.generate.side_effect = LLMProviderError("API error")

        with pytest.raises(QueryRepairFailed) as exc_info:
            attempt_repair(
                user_id="test-user",
                original_ir=_ORIGINAL_IR,
                original_sql=_ORIGINAL_SQL,
                error_message="unfixable error",
                columns_description=_COLUMNS_DESC,
                csv_bytes=_CSV_BYTES,
            )

        err = exc_info.value
        assert err.original_sql == _ORIGINAL_SQL
        assert "unfixable error" in err.original_error

    @patch("app.llm.repair.GroqAdapter")
    def test_repair_still_fails_execution(self, mock_adapter_cls):
        """If the repaired IR still fails execution, QueryRepairFailed."""
        mock_adapter = MagicMock()
        mock_adapter_cls.return_value = mock_adapter

        # Return an IR with a still-wrong column
        still_bad_ir = {
            "ir_version": "1.2",
            "kind": "structured",
            "source": "sales",
            "operation": "aggregation",
            "metrics": [{"column": "nonexistent_col", "aggregation": "SUM", "alias": "total"}],
            "confidence": 0.6,
        }
        mock_adapter.generate.return_value = still_bad_ir

        with pytest.raises(QueryRepairFailed) as exc_info:
            attempt_repair(
                user_id="test-user",
                original_ir=_ORIGINAL_IR,
                original_sql=_ORIGINAL_SQL,
                error_message="original error",
                columns_description=_COLUMNS_DESC,
                csv_bytes=_CSV_BYTES,
            )

        err = exc_info.value
        assert "original error" in err.original_error
        assert "Repaired query still failed" in err.repair_error

    @patch("app.llm.repair.GroqAdapter")
    def test_repair_failed_message_is_clear(self, mock_adapter_cls):
        """The QueryRepairFailed message should include both errors."""
        from app.llm.provider_interface import LLMProviderError

        mock_adapter = MagicMock()
        mock_adapter_cls.return_value = mock_adapter
        mock_adapter.generate.side_effect = LLMProviderError("timeout")

        with pytest.raises(QueryRepairFailed) as exc_info:
            attempt_repair(
                user_id="test-user",
                original_ir=_ORIGINAL_IR,
                original_sql=_ORIGINAL_SQL,
                error_message="column not found",
                columns_description=_COLUMNS_DESC,
                csv_bytes=_CSV_BYTES,
            )

        msg = str(exc_info.value)
        assert "column not found" in msg
        assert "repair" in msg.lower() or "timeout" in msg.lower()
