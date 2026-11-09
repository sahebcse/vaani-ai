"""Application settings. Every setting is env-overridable; see README."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VAANI_", extra="ignore")

    app_name: str = "vaani"
    app_version: str = "0.1.0"
    log_level: str = "INFO"

    postgres_dsn: str = "postgresql://vaani:vaani@localhost:5432/vaani"
    redis_url: str = "redis://localhost:6379/0"
    kafka_bootstrap_servers: str = "localhost:29092"
    opensearch_url: str = "http://localhost:9200"

    sarvam_base_url: str = "http://localhost:8001"
    sarvam_api_key: str = "local-mock"
    sarvam_timeout_seconds: float = 10.0
    retriever: str = "keyword"
    admin_key: str = "change-me-local-only"
    eval_dataset_path: str = "fixtures/eval/dataset.jsonl"
    archive_path: str = "var/call-archive/calls.jsonl"

    default_tenant: str = "demo-nbfc"
    eval_score_threshold: float = 0.7


def get_settings() -> Settings:
    return Settings()
