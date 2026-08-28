"""
LLMProvider — abstract base class for all LLM adapters.

Implemented in ticket L5.1 (Session 5).

Contract:
  generate(user_id, purpose, messages, output_schema) -> dict
    user_id        : str — UUID of the calling user; the adapter fetches
                     THAT user's own API key via key_store.fetch_key_for_llm()
                     Never accepts a global/platform API key.
    purpose        : str — human-readable label for llm_usage logging
    messages       : list of {"role": "system"|"user"|"assistant", "content": str}
    output_schema  : dict | None — JSON Schema the response must validate against
                     (None = raw text response, returned as {"text": ...})
  Returns a dict that passes jsonschema.validate(result, output_schema).
  Raises LLMValidationError if the response doesn't match the schema.
  Raises LLMProviderError for network/API-level failures.
  Raises fastapi.HTTPException(402) if the user has no API key configured.

Every adapter MUST:
  - Fetch the user's own key via key_store (never a global env var key).
  - Log an llm_usage row after each call (input/output tokens, cost estimate,
    user_id of the key owner).
  - Never be called directly from outside backend/app/llm/adapters/ — all
    LLM calls go through this interface.
"""
from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """Abstract LLM provider. Implement one adapter per provider."""

    @abstractmethod
    def generate(
        self,
        user_id: str,
        purpose: str,
        messages: list[dict[str, str]],
        output_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Call the underlying LLM and return a validated dict.

        Raises:
            HTTPException(402): if the user has no API key configured.
            LLMValidationError: if the model output doesn't match output_schema.
            LLMProviderError: for network/API-level failures.
        """
        ...


class LLMProviderError(Exception):
    """Raised for network or API-level failures from the LLM provider."""


class LLMValidationError(Exception):
    """Raised when the LLM response doesn't match the expected output schema."""

