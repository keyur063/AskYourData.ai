"""
Environment-driven settings for AskYourData.ai backend.

All values are read from environment variables (or .env in local dev).
Never hardcode secrets here — populate .env from .env.example and fill
real values yourself outside the agent conversation.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    database_url: str = ""

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

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
