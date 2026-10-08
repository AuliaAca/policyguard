"""Semua konfigurasi dibaca dari environment variable (atau file .env).

Tidak ada nilai rahasia di kode. Nilai rahasia (API key, password DB) memakai SecretStr
supaya tidak ikut tercetak saat objek settings di-log.
"""
from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Infrastruktur
    database_url: str = "sqlite:///./policyguard.db"
    redis_url: str = ""                               # kosong = batch nonaktif (tanpa Redis)
    service_api_keys: SecretStr = SecretStr("")      # dipisah koma: "key-sistem-listing,key-dashboard"

    # Pipeline
    pipeline_mode: str = "llm"                        # "llm" atau "rules_only"
    policies_dir: str = "data/policies"
    rules_path: str = "data/rules/rules.json"

    # LLM
    openai_api_key: SecretStr | None = None
    openai_base_url: str | None = None                # kosong = API resmi OpenAI
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float | None = 0.0
    llm_timeout_seconds: float = 20.0
    llm_max_retries: int = 2

    # Retrieval
    retrieval_mode: str = "topk"                      # "topk" (RAG) atau "all" (semua pasal)
    retrieval_top_k: int = 5
    embedding_provider: str = "openai"                # "openai" atau "local"
    embedding_model: str = "text-embedding-3-small"

    # Threshold keputusan (ADR-008): placeholder, tetapkan dari hasil evaluasi dev set
    t_reject: float = 0.8
    t_approve: float = 0.8

    log_level: str = "INFO"

    @field_validator("llm_temperature", "openai_base_url", mode="before")
    @classmethod
    def _empty_is_none(cls, v):
        # "LLM_TEMPERATURE=" di .env berarti "jangan kirim parameter ini", bukan error.
        return None if isinstance(v, str) and v.strip() == "" else v

    @property
    def api_keys(self) -> set[str]:
        return {k.strip() for k in self.service_api_keys.get_secret_value().split(",") if k.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
