"""
Groq adapter for AskYourData.ai.

Implemented in ticket L5.1 (Session 5).

This is the ONLY place in the codebase that imports or calls the openai SDK
(pointed at Groq's base URL — Groq's API is OpenAI-schema-compatible).
All other modules must go through app.llm.provider_interface.LLMProvider.

BYOK: the adapter takes a user_id, calls key_store.fetch_key_for_llm() to
get that user's decrypted Groq API key, and uses it for the API call. There
is no platform-wide GROQ_API_KEY. If the user has no key configured, the
adapter raises a clear HTTP 402 / user-facing error (not a generic failure).
"""
from __future__ import annotations

import json
from typing import Any

import jsonschema
from openai import OpenAI, APIConnectionError, APIStatusError

from app.core.config import settings
from app.core.logging import get_logger
from app.llm.key_store import fetch_key_for_llm
from app.llm.provider_interface import (
    LLMProvider,
    LLMProviderError,
    LLMValidationError,
)

logger = get_logger(__name__)

# Default model — can be overridden per-user via the groq_model column.
_DEFAULT_MODEL = "llama-3.3-70b-versatile"


class GroqAdapter(LLMProvider):
    """OpenAI-compatible adapter for Groq's API.

    Instantiate once per request; it lazily fetches the user's key on
    the first generate() call.
    """

    def generate(
        self,
        user_id: str,
        purpose: str,
        messages: list[dict[str, str]],
        output_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call Groq and return a validated dict.

        Raises:
            HTTPException(402): if the user has no API key configured.
            LLMValidationError: if the model output doesn't match output_schema.
            LLMProviderError: for network/API-level failures.
        """
        # --- Fetch user's key (raises HTTP 402 if absent) ----------------
        api_key, model_override = fetch_key_for_llm(user_id)
        model = model_override or _DEFAULT_MODEL

        # --- Build OpenAI client pointed at Groq -------------------------
        client = OpenAI(
            api_key=api_key,
            base_url=settings.groq_base_url,
        )

        # --- Build request kwargs ----------------------------------------
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0,  # deterministic for structured output
        }
        if output_schema is not None:
            kwargs["response_format"] = {"type": "json_object"}

        # --- Call Groq API ------------------------------------------------
        try:
            completion = client.chat.completions.create(**kwargs)
        except APIConnectionError as exc:
            logger.error("Groq connection error for user=%s: %s", user_id, exc)
            raise LLMProviderError(
                f"Could not connect to Groq API: {exc}"
            ) from exc
        except APIStatusError as exc:
            logger.error(
                "Groq API error for user=%s: status=%s body=%s",
                user_id, exc.status_code, exc.body,
            )
            raise LLMProviderError(
                f"Groq API returned status {exc.status_code}: {exc.message}"
            ) from exc

        # --- Extract response --------------------------------------------
        choice = completion.choices[0]
        raw_text = choice.message.content or ""

        # --- Log usage ---------------------------------------------------
        usage = completion.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        logger.info(
            "LLM call: purpose=%s model=%s user=%s "
            "input_tokens=%d output_tokens=%d",
            purpose, model, user_id,
            input_tokens, output_tokens,
        )

        # Log to llm_usage table (best-effort — don't fail the request)
        try:
            _log_usage(
                user_id=user_id,
                provider="groq",
                model=model,
                purpose=purpose,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        except Exception as exc:
            logger.warning("Failed to log llm_usage: %s", exc)

        # --- Parse and validate ------------------------------------------
        if output_schema is None:
            return {"text": raw_text}

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise LLMValidationError(
                f"Groq returned non-JSON response: {raw_text[:200]}"
            ) from exc

        try:
            jsonschema.validate(parsed, output_schema)
        except jsonschema.ValidationError as exc:
            raise LLMValidationError(
                f"Groq response failed schema validation: {exc.message}"
            ) from exc

        return parsed


def _log_usage(
    user_id: str,
    provider: str,
    model: str,
    purpose: str,
    input_tokens: int,
    output_tokens: int,
) -> None:
    """Insert a row into the llm_usage table (best-effort)."""
    from app.core.supabase_client import service_client

    service_client().table("llm_usage").insert({
        "user_id": user_id,
        "provider": provider,
        "model": model,
        "purpose": purpose,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }).execute()


