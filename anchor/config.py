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
    vertex_project_id: str
    vertex_location: str
    google_application_credentials: str
    generation_model: str = "gemini-2.5-flash"
    embedding_model: str = "gemini-embedding-2"
    embedding_dimension: int = 768
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    cohere_api_key: str
    rerank_model: str = "rerank-v4.0-pro"
    rate_limit_rpm: int = 10
    rate_limit_rpd: int = 100
    max_query_chars: int = 800
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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

