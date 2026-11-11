from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8080
    allowed_origins: str = "http://localhost:4173"

    openai_api_key: SecretStr | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-5.6-sol"
    openai_reasoning_effort: Literal["none", "low", "medium", "high", "xhigh", "max"] = "medium"
    openai_skill_id: str = "skill_6af440f78bb08191bcd8bc8691b228bb05903870db4bc490"
    openai_skill_version: str = "latest"
    openai_request_timeout_seconds: float = 120.0

    storage_backend: Literal["firestore", "memory"] = "firestore"
    firestore_project_id: str | None = None
    firestore_collection: str = "work_sessions"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
