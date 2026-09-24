"""Application settings — fails fast if required env vars are missing."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(..., alias="DATABASE_URL")
    vapi_api_key: str = Field(..., alias="VAPI_API_KEY")
    vapi_public_key: str = Field(..., alias="VAPI_PUBLIC_KEY")
    vapi_webhook_secret: str = Field(..., alias="VAPI_WEBHOOK_SECRET")
    # Optional on first Render boot; set after you know the service URL, then run setup_vapi
    public_base_url: str = Field(default="http://localhost:8000", alias="PUBLIC_BASE_URL")

    deepgram_api_key: str | None = Field(default=None, alias="DEEPGRAM_API_KEY")
    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    google_api_key: str | None = Field(default=None, alias="GOOGLE_API_KEY")
    llm_provider: str = Field(default="groq", alias="LLM_PROVIDER")

    vapi_assistant_id: str | None = Field(default=None, alias="VAPI_ASSISTANT_ID")
    vapi_phone_number_id: str | None = Field(default=None, alias="VAPI_PHONE_NUMBER_ID")
    vapi_phone_number: str | None = Field(default=None, alias="VAPI_PHONE_NUMBER")

    clinic_timezone: str = Field(default="America/New_York", alias="CLINIC_TIMEZONE")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    dashboard_user: str | None = Field(default=None, alias="DASHBOARD_USER")
    dashboard_password: str | None = Field(default=None, alias="DASHBOARD_PASSWORD")

    app_name: str = "CareCloud Voice Patient Registration"
    tool_timeout_seconds: float = 8.0


@lru_cache
def get_settings() -> Settings:
    return Settings()


def sqlalchemy_url(url: str | None = None) -> str:
    """Prefer psycopg (v3) driver for SQLAlchemy."""
    raw = url or get_settings().database_url
    if raw.startswith("postgresql+psycopg://") or raw.startswith("postgresql+psycopg2://"):
        return raw
    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://") :]
    if raw.startswith("postgresql://"):
        return "postgresql+psycopg://" + raw[len("postgresql://") :]
    return raw
