from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Anchor"
    environment: str = "development"
    log_level: str = "INFO"
    database_url: str
    gemini_api_key: str = ""
    gemini_api_base_url: str = "https://generativelanguage.googleapis.com/v1beta/models"
    generation_model: str = "gemini-3-flash-preview"
    embedding_model: str = "gemini-embedding-2"
    embedding_dimension: int = 768
    embedding_batch_size: int = 32
    embedding_batch_pause_seconds: float = 35.0
    gemini_max_retries: int = 8
    gemini_retry_base_seconds: float = 20.0
    gemini_retry_max_seconds: float = 180.0
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    cohere_api_key: str = ""
    rerank_model: str = "rerank-v4.0-pro"
    rate_limit_rpm: int = 10
    rate_limit_rpd: int = 100
    max_query_chars: int = 800
    max_completion_tokens: int = 512
    rrf_constant: int = 60
    lexical_candidate_count: int = 30
    dense_candidate_count: int = 30
    rerank_candidate_count: int = 20
    rerank_top_k: int = 8
    final_context_top_k: int = 5
    rerank_min_top_score: float = 0.35
    rerank_min_support_score: float = 0.20
    rerank_min_support_count: int = 2
    cors_origin: str = "http://localhost:3000"
    request_timeout_seconds: float = 15.0
    metrics_namespace: str = "anchor"
    corpus_manifest_path: Path = Path("corpus/manifest.yaml")
    raw_corpus_dir: Path = Path("corpus/raw")

    def validate_ingest_runtime(self) -> None:
        self._require("GEMINI_API_KEY", self.gemini_api_key)

    def validate_query_runtime(self) -> None:
        self._require("GEMINI_API_KEY", self.gemini_api_key)
        self._require("COHERE_API_KEY", self.cohere_api_key)
        if self.environment == "production":
            self._require("LANGFUSE_PUBLIC_KEY", self.langfuse_public_key)
            self._require("LANGFUSE_SECRET_KEY", self.langfuse_secret_key)

    @staticmethod
    def _require(name: str, value: str) -> None:
        if not value:
            raise ValueError(f"{name} is required for this runtime path")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
