"""
LLMProvider — abstract base class for all LLM adapters.

Implemented in ticket L5.1 (Session 5).

Contract:
  generate(purpose, messages, output_schema) -> dict
    purpose        : str — human-readable label for llm_usage logging
    messages       : list of {"role": "system"|"user"|"assistant", "content": str}
    output_schema  : dict | None — JSON Schema the response must validate against
                     (None = raw text response, returned as {"text": ...})
  Returns a dict that passes jsonschema.validate(result, output_schema).
  Raises LLMValidationError if the response doesn't match the schema after
  MAX_QUERY_REPAIR_ATTEMPTS retries (handled by the caller, not here).

Every adapter MUST:
  - Log an llm_usage row after each call (input/output tokens, cost estimate).
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
        purpose: str,
        messages: list[dict[str, str]],
        output_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Call the underlying LLM and return a validated dict.

        Raises:
            LLMValidationError: if the model output doesn't match output_schema.
            LLMProviderError: for network/API-level failures.
        """
        ...


class LLMProviderError(Exception):
    """Raised for network or API-level failures from the LLM provider."""


class LLMValidationError(Exception):
    """Raised when the LLM response doesn't match the expected output schema."""
