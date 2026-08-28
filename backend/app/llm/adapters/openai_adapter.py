"""
OpenAI adapter for AskYourData.ai.

Implemented in ticket L5.1 (Session 5).

This is the ONLY place in the codebase that imports or calls the openai SDK.
All other modules must go through app.llm.provider_interface.LLMProvider.
"""
# TODO L5.1: implement OpenAIAdapter(LLMProvider)
#   - use settings.openai_api_key and settings.openai_model
#   - call openai.chat.completions.create(response_format={"type": "json_object"})
#   - validate response against output_schema with jsonschema
#   - log llm_usage row via service_client()
#   - raise LLMValidationError / LLMProviderError as appropriate
