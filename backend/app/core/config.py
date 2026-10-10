from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "RepoGuard AI"
    database_url: str | None = None
    cors_origins: str = "http://localhost:5173"
    github_token: str | None = None
    max_files: int = 2500
    max_file_bytes: int = 500_000
    max_total_bytes: int = 25_000_000
    request_timeout: float = 20.0
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
