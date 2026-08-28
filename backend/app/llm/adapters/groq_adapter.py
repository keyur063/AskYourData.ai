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
# TODO L5.1: implement GroqAdapter(LLMProvider)
#   - __init__(self, user_id: str)
#   - generate() fetches user's key via key_store.fetch_key_for_llm(user_id)
#   - uses openai.OpenAI(base_url=settings.groq_base_url, api_key=user_key)
#   - requests response_format={"type": "json_object"} for structured output
#   - validates response against output_schema with jsonschema
#   - logs llm_usage row (provider="groq", user_id=user_id)
#   - raises LLMValidationError / LLMProviderError as appropriate

