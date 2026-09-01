"""
Tests for app.llm.adapters.groq_adapter — L5.1 acceptance criteria (offline).

Mocks the OpenAI SDK and key_store to verify adapter logic without
calling the real Groq API. Live integration tested via manual L5.1
verification.
"""
from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

# Set up test encryption key before any imports
os.environ.setdefault("ENCRYPTION_KEY", "test")
from cryptography.fernet import Fernet

_TEST_KEY = Fernet.generate_key().decode()
os.environ["ENCRYPTION_KEY"] = _TEST_KEY

from app.core.config import Settings
import app.core.config as config_mod
config_mod.settings = Settings()

from app.llm.adapters.groq_adapter import GroqAdapter
from app.llm.provider_interface import LLMProviderError, LLMValidationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_completion(content: str, input_tokens: int = 10, output_tokens: int = 20):
    """Build a mock OpenAI ChatCompletion response."""
    usage = MagicMock()
    usage.prompt_tokens = input_tokens
    usage.completion_tokens = output_tokens

    message = MagicMock()
    message.content = content

    choice = MagicMock()
    choice.message = message

    completion = MagicMock()
    completion.choices = [choice]
    completion.usage = usage
    return completion


_TEST_SCHEMA = {
    "type": "object",
    "required": ["source", "operation"],
    "properties": {
        "source": {"type": "string"},
        "operation": {"type": "string"},
    },
}


# =========================================================================
# Test GroqAdapter.generate()
# =========================================================================

class TestGroqAdapter:
    """Test the GroqAdapter with mocked OpenAI client and key_store."""

    @patch("app.llm.adapters.groq_adapter.fetch_key_for_llm")
    @patch("app.llm.adapters.groq_adapter.OpenAI")
    def test_generate_with_schema(self, mock_openai_cls, mock_fetch):
        """generate() with output_schema parses JSON and validates."""
        mock_fetch.return_value = ("gsk_test_key", None)
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        response_body = json.dumps({"source": "sales", "operation": "aggregation"})
        mock_client.chat.completions.create.return_value = _mock_completion(response_body)

        adapter = GroqAdapter()
        result = adapter.generate(
            user_id="test-user-1",
            purpose="planner",
            messages=[{"role": "user", "content": "sum of revenue"}],
            output_schema=_TEST_SCHEMA,
        )

        assert result == {"source": "sales", "operation": "aggregation"}
        # Verify OpenAI was called with json_object response_format
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["response_format"] == {"type": "json_object"}

    @patch("app.llm.adapters.groq_adapter.fetch_key_for_llm")
    @patch("app.llm.adapters.groq_adapter.OpenAI")
    def test_generate_without_schema(self, mock_openai_cls, mock_fetch):
        """generate() without output_schema returns {text: ...}."""
        mock_fetch.return_value = ("gsk_test_key", None)
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_completion("Hello world")

        adapter = GroqAdapter()
        result = adapter.generate(
            user_id="test-user-1",
            purpose="chat",
            messages=[{"role": "user", "content": "hi"}],
        )

        assert result == {"text": "Hello world"}
        # No response_format should be set for plain text
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "response_format" not in call_kwargs

    @patch("app.llm.adapters.groq_adapter.fetch_key_for_llm")
    @patch("app.llm.adapters.groq_adapter.OpenAI")
    def test_schema_validation_error(self, mock_openai_cls, mock_fetch):
        """generate() raises LLMValidationError on schema mismatch."""
        mock_fetch.return_value = ("gsk_test_key", None)
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        # Missing required 'operation' field
        response_body = json.dumps({"source": "sales"})
        mock_client.chat.completions.create.return_value = _mock_completion(response_body)

        adapter = GroqAdapter()
        with pytest.raises(LLMValidationError, match="schema validation"):
            adapter.generate(
                user_id="test-user-1",
                purpose="planner",
                messages=[{"role": "user", "content": "test"}],
                output_schema=_TEST_SCHEMA,
            )

    @patch("app.llm.adapters.groq_adapter.fetch_key_for_llm")
    @patch("app.llm.adapters.groq_adapter.OpenAI")
    def test_non_json_response(self, mock_openai_cls, mock_fetch):
        """generate() raises LLMValidationError on non-JSON response."""
        mock_fetch.return_value = ("gsk_test_key", None)
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_completion("not json!")

        adapter = GroqAdapter()
        with pytest.raises(LLMValidationError, match="non-JSON"):
            adapter.generate(
                user_id="test-user-1",
                purpose="planner",
                messages=[{"role": "user", "content": "test"}],
                output_schema=_TEST_SCHEMA,
            )

    @patch("app.llm.adapters.groq_adapter.fetch_key_for_llm")
    @patch("app.llm.adapters.groq_adapter.OpenAI")
    def test_api_connection_error(self, mock_openai_cls, mock_fetch):
        """generate() wraps APIConnectionError as LLMProviderError."""
        from openai import APIConnectionError
        mock_fetch.return_value = ("gsk_test_key", None)
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.side_effect = APIConnectionError(
            request=MagicMock()
        )

        adapter = GroqAdapter()
        with pytest.raises(LLMProviderError, match="connect"):
            adapter.generate(
                user_id="test-user-1",
                purpose="planner",
                messages=[{"role": "user", "content": "test"}],
            )

    @patch("app.llm.adapters.groq_adapter.fetch_key_for_llm")
    @patch("app.llm.adapters.groq_adapter.OpenAI")
    def test_user_model_override(self, mock_openai_cls, mock_fetch):
        """If the user has a model override, it's used instead of the default."""
        mock_fetch.return_value = ("gsk_test_key", "llama-3.1-8b-instant")
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_completion("hi")

        adapter = GroqAdapter()
        adapter.generate(
            user_id="test-user-1",
            purpose="chat",
            messages=[{"role": "user", "content": "hi"}],
        )

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "llama-3.1-8b-instant"

    @patch("app.llm.adapters.groq_adapter.fetch_key_for_llm")
    @patch("app.llm.adapters.groq_adapter.OpenAI")
    def test_uses_groq_base_url(self, mock_openai_cls, mock_fetch):
        """OpenAI client must be configured with settings.groq_base_url."""
        mock_fetch.return_value = ("gsk_test_key", None)
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_completion("hi")

        adapter = GroqAdapter()
        adapter.generate(
            user_id="test-user-1",
            purpose="chat",
            messages=[{"role": "user", "content": "hi"}],
        )

        call_kwargs = mock_openai_cls.call_args.kwargs
        assert "groq" in call_kwargs["base_url"]
