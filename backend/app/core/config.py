"""
Environment-driven settings for AskYourData.ai backend.

All values are read from environment variables (or .env in local dev).
Never hardcode secrets here — populate .env from .env.example and fill
real values yourself outside the agent conversation.

LLM model: each user brings their own Groq API key (BYOK) — there is NO
platform-wide GROQ_API_KEY here. GROQ_BASE_URL is the one platform-wide
Groq setting (same endpoint for every user). Per-user keys are stored
encrypted in `user_api_keys` and decrypted in memory by the Groq adapter
when making a call on that user's behalf.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    database_url: str = ""

    # Groq — platform-wide base URL only; no global API key (BYOK)
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # Symmetric encryption key for per-user stored Groq API keys.
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Losing this key makes every stored user API key unrecoverable.
    encryption_key: str = ""

    # Query pipeline limits (lean scope: hard caps, no LOW/MED/HIGH)
    max_query_repair_attempts: int = 1
    max_file_size_mb: int = 5
    max_rows_scanned: int = 1_000_000
    query_timeout_seconds: int = 10

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


# Single shared instance — import this wherever settings are needed.
settings = Settings()
