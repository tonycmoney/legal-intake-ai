"""Settings from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./intake.db"

    # Claude. The intake chat is unavailable (HTTP 503) until a key is set.
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5-5"
    anthropic_effort: str = "low"  # intake turns need speed more than deep reasoning
    max_output_tokens: int = 2048

    # Staff dashboard. Disabled (HTTP 503) until a password is set.
    staff_password: str | None = None
    session_hours: int = 8

    # The fictional firm shown on the intake page.
    firm_name: str = "Hudson Row Legal"
    firm_phone: str = "(555) 010-0199"

    # Abuse and cost controls
    max_message_chars: int = 2000
    max_turns_per_session: int = 30
    rate_limit_messages: int = 20  # per client IP...
    rate_limit_window_s: int = 600  # ...per 10 minutes

    # Prospective client data from declined intakes is purged after this many days.
    declined_retention_days: int = 30

    seed_conflicts: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
