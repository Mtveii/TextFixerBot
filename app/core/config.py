"""Central configuration (pydantic-settings)."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = Field(default="", alias="BOT_TOKEN")

    # OpenAI (optional)
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")

    # Groq (OpenAI-compatible, fast). Default model is current production one.
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    groq_base_url: str = Field(default="https://api.groq.com/openai/v1", alias="GROQ_BASE_URL")
    groq_model: str = Field(default="openai/gpt-oss-20b", alias="GROQ_MODEL")
    groq_vision_model: str = Field(
        default="qwen/qwen3.8-27b", alias="GROQ_VISION_MODEL"
    )
    groq_stt_model: str = Field(default="whisper-large-v3-turbo", alias="GROQ_STT_MODEL")

    # Gemini (OpenAI-compatible endpoint)
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_base_url: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta/openai/", alias="GEMINI_BASE_URL"
    )
    gemini_model: str = Field(default="gemini-3.6-flash", alias="GEMINI_MODEL")

    openai_timeout: int = Field(default=60, alias="OPENAI_TIMEOUT")

    # Order in which backends are tried, e.g. "groq,gemini,openai"
    llm_order: str = Field(default="groq,gemini,openai", alias="LLM_ORDER")

    database_url: str = Field(default="sqlite+aiosqlite:///./data.db", alias="DATABASE_URL")
    postgres_url: str = Field(default="", alias="POSTGRES_URL")
    redis_url: str = Field(default="", alias="REDIS_URL")
    webhook_url: str = Field(default="", alias="WEBHOOK_URL")
    webhook_path: str = Field(default="/webhook", alias="WEBHOOK_PATH")
    webhook_secret: str = Field(default="", alias="WEBHOOK_SECRET")
    webhook_port: int = Field(default=8080, alias="WEBHOOK_PORT")
    admin_ids: str = Field(default="", alias="ADMIN_IDS")

    free_daily_limit: int = Field(default=20, alias="FREE_DAILY_LIMIT")
    premium_daily_limit: int = Field(default=500, alias="PREMIUM_DAILY_LIMIT")
    premium_stars_price: int = Field(default=150, alias="PREMIUM_STARS_PRICE")
    default_language: str = Field(default="ru", alias="DEFAULT_LANGUAGE")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @property
    def admin_id_set(self) -> set[int]:
        out: set[int] = set()
        for part in self.admin_ids.replace(";", ",").split(","):
            part = part.strip()
            if part.isdigit():
                out.add(int(part))
        return out

    @property
    def effective_database_url(self) -> str:
        if self.database_url.startswith("postgres"):
            return self.database_url
        if self.postgres_url:
            return self.postgres_url
        return self.database_url

    @property
    def llm_configured(self) -> bool:
        return bool(self.openai_api_key or self.groq_api_key or self.gemini_api_key)

    @property
    def backend_order(self) -> list[str]:
        order = [p.strip().lower() for p in self.llm_order.split(",") if p.strip()]
        return order or ["groq", "gemini", "openai"]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
