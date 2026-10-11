from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "RepoGuard AI"
    database_url: str | None = None
    cors_origins: str = "http://localhost:5173"
    github_token: str | None = None
    openai_api_key: str | None = Field(default=None, max_length=500)
    rag_embedding_model: str = Field(default="text-embedding-3-small", min_length=1, max_length=200)
    rag_chat_model: str = Field(default="gpt-4o-mini", min_length=1, max_length=200)
    rag_embedding_dimensions: int = Field(default=1536, ge=1, le=4096)
    rag_embedding_batch_size: int = Field(default=32, ge=1, le=64)
    rag_embedding_max_chunks: int = Field(default=256, ge=1, le=2000)
    rag_chunk_max_chars: int = Field(default=8000, ge=128, le=16000)
    rag_retrieved_chunks: int = Field(default=5, ge=1, le=10)
    rag_context_max_chars: int = Field(default=12000, ge=1000, le=30000)
    rag_min_similarity: float = Field(default=0.2, ge=-1.0, le=1.0)
    rag_provider_timeout: float = Field(default=12.0, ge=1.0, le=60.0)
    rag_request_timeout: float = Field(default=20.0, ge=1.0, le=90.0)
    rag_provider_response_bytes: int = Field(default=2_000_000, ge=1024, le=5_000_000)
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
