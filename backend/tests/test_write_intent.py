"""
Tests for the write-intent pre-check in POST /workspaces/{id}/query.

L7.3 acceptance: questions containing delete/drop/insert/update/etc. as
whole words must return 400 with a clear refusal. Questions that merely
contain those strings inside column names or data values must not be
blocked.
"""
from __future__ import annotations

import os
from unittest.mock import patch, MagicMock

import pytest

os.environ.setdefault("ENCRYPTION_KEY", "test")
from cryptography.fernet import Fernet
os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()

from app.api.query import _WRITE_INTENT_RE


# ---------------------------------------------------------------------------
# Regex unit tests (no HTTP stack needed)
# ---------------------------------------------------------------------------

class TestWriteIntentRegex:
    """_WRITE_INTENT_RE must match mutation words as whole words only."""

    @pytest.mark.parametrize("question", [
        "delete all rows where region is North",
        "Delete the records for Widget A",
        "DROP the table",
        "drop all data",
        "insert a new row with region=East",
        "update the price for Widget B",
        "alter the schema",
        "truncate the dataset",
        "remove all South orders",
        "erase Widget C rows",
        "destroy the data",
        "wipe everything",
        "can you delete this for me?",
        "please remove duplicates",
    ])
    def test_blocked_mutation_questions(self, question: str):
        assert _WRITE_INTENT_RE.search(question) is not None, (
            f"Expected '{question}' to be blocked but was not"
        )

    @pytest.mark.parametrize("question", [
        "What is the total quantity?",
        "Show rows where region is North",
        "Top 3 products by revenue",
        "Average price by category",
        "How many unique products?",
        # Column names containing blocked substrings must NOT trigger
        "What is the total for the updated_at column?",
        "Show the delete_flag values",
        # Possessives / partial matches must NOT trigger
        "What's the removal rate?",   # 'remove' won't match 'removal'
    ])
    def test_allowed_read_questions(self, question: str):
        assert _WRITE_INTENT_RE.search(question) is None, (
            f"Expected '{question}' to be allowed but was blocked"
        )


# ---------------------------------------------------------------------------
# HTTP integration test via TestClient
# ---------------------------------------------------------------------------

class TestWriteIntentEndpoint:
    """POST /workspaces/{id}/query returns 400 for mutation questions."""

    def _make_client_with_auth(self):
        """TestClient with require_user overridden to return a fake user."""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.core.security import require_user, CurrentUser

        mock_user = MagicMock(spec=CurrentUser)
        mock_user.user_id = "test-user"
        mock_user.jwt = "test-jwt"

        app.dependency_overrides[require_user] = lambda: mock_user
        client = TestClient(app, raise_server_exceptions=False)
        return client, app, require_user

    def test_delete_question_returns_400(self):
        """A delete question must return 400 before the planner is called."""
        client, app, require_user = self._make_client_with_auth()
        try:
            with patch("app.api.query.get_table_with_columns") as mock_catalog:
                mock_catalog.return_value = {
                    "name": "sales",
                    "columns": [{"name": "region", "data_type": "text"}],
                }
                with patch("app.api.query.plan_query") as mock_planner:
                    resp = client.post(
                        "/workspaces/00000000-0000-0000-0000-000000000001/query",
                        json={
                            "question": "delete all rows where region is North",
                            "table_id": "00000000-0000-0000-0000-000000000002",
                        },
                    )
                    assert resp.status_code == 400
                    assert "read-only" in resp.json()["detail"].lower()
                    mock_planner.assert_not_called()
        finally:
            app.dependency_overrides.clear()

    def test_safe_question_not_blocked(self):
        """A normal read question must reach the planner (not blocked)."""
        from app.llm.provider_interface import LLMProviderError

        client, app, require_user = self._make_client_with_auth()
        try:
            with patch("app.api.query.get_table_with_columns") as mock_catalog:
                mock_catalog.return_value = {
                    "name": "sales",
                    "columns": [{"name": "region", "data_type": "text"}],
                }
                with patch("app.api.query.plan_query") as mock_planner:
                    mock_planner.side_effect = LLMProviderError("no key")
                    resp = client.post(
                        "/workspaces/00000000-0000-0000-0000-000000000001/query",
                        json={
                            "question": "total quantity by region",
                            "table_id": "00000000-0000-0000-0000-000000000002",
                        },
                    )
                    # Planner was called — question was NOT blocked
                    mock_planner.assert_called_once()
        finally:
            app.dependency_overrides.clear()

