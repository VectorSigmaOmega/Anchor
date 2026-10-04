from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator
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
    generation_provider: Literal["gemini", "openai"] = "gemini"
    embedding_provider: Literal["gemini", "openai"] = "gemini"
    openai_api_key: str = ""
    openai_api_base_url: str = "https://api.openai.com/v1"
    openai_reasoning_effort: str | None = None
    gemini_api_key: str = ""
    gemini_api_base_url: str = "https://generativelanguage.googleapis.com/v1beta/models"
    generation_model: str = "gemini-3.1-flash-lite"
    multipart_generation_model: str = "gemini-3.5-flash-lite"
    workflow_draft_model: str | None = None
    generation_thinking_level: Literal["minimal", "low", "medium", "high"] = "minimal"
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
    rate_limit_rpm: int = Field(default=10, gt=0)
    rate_limit_rpd: int = Field(default=100, gt=0)
    max_query_chars: int = Field(default=4000, gt=0)
    max_completion_tokens: int = 2048
    multipart_workflow_enabled: bool = False
    linear_source_comparison_enabled: bool = False
    retrieval_plan_model: str | None = None
    workflow_topic_review_enabled: bool = True
    workflow_timeout_seconds: float = Field(default=60.0, gt=0)
    multipart_max_completion_tokens: int = 4096
    multipart_max_citations: int = 32
    multipart_context_top_k: int = 16
    multipart_rerank_candidate_count: int = 40
    max_citations: int = 24
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
    rerank_request_timeout_seconds: float = Field(default=7.0, gt=0)
    query_timeout_seconds: float = Field(default=25.0, gt=0)
    metrics_namespace: str = "anchor"
    session_cookie_name: str = "anchor_session"
    session_cookie_max_age_days: int = 400
    corpus_manifest_path: Path = Path("corpus/manifest.yaml")
    raw_corpus_dir: Path = Path("corpus/raw")

    @model_validator(mode="before")
    @classmethod
    def provider_model_defaults(cls, values: Any) -> Any:
        if isinstance(values, dict):
            if not values.get("generation_model"):
                values["generation_model"] = "gpt-4.1-mini" if values.get("generation_provider") == "openai" else "gemini-3.1-flash-lite"
            if not values.get("embedding_model"):
                values["embedding_model"] = (
                    "text-embedding-3-small" if values.get("embedding_provider") == "openai" else "gemini-embedding-2"
                )
        return values

    def validate_ingest_runtime(self) -> None:
        self._validate_provider_key(self.embedding_provider)

    def validate_query_runtime(self) -> None:
        self._validate_provider_key(self.embedding_provider)
        self._validate_provider_key(self.generation_provider)
        self._require("COHERE_API_KEY", self.cohere_api_key)
        if self.environment == "production":
            self._require("LANGFUSE_PUBLIC_KEY", self.langfuse_public_key)
            self._require("LANGFUSE_SECRET_KEY", self.langfuse_secret_key)

    def _validate_provider_key(self, provider: str) -> None:
        if provider == "openai":
            self._require("OPENAI_API_KEY", self.openai_api_key)
        else:
            self._require("GEMINI_API_KEY", self.gemini_api_key)

    @staticmethod
    def _require(name: str, value: str) -> None:
        if not value:
            raise ValueError(f"{name} is required for this runtime path")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
