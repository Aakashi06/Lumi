import os
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Bound CPU pools before importing NLP/numerical libraries; respect explicit overrides.
for variable in (
    "OMP_NUM_THREADS",
    "BLIS_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
):
    os.environ.setdefault(variable, "2")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="LUMI_", extra="ignore")
    spacy_model: str = "en_core_web_sm"
    enable_embeddings: bool = False
    initial_graph_chunks: int = Field(default=4, ge=1, le=8)
    extraction_batch_size: int = Field(default=8, ge=1, le=32)
    graph_node_limit: int = Field(default=75, ge=50, le=100)
    graph_expansion_limit: int = Field(default=200, ge=100, le=200)
    database_url: str = "sqlite:///./data/lumi.db"
    model_url: str = "http://127.0.0.1:8080/v1"
    embedding_url: str = "http://127.0.0.1:8081/v1"
    model_id: str = "Qwen3-4B-Instruct-2507"
    embedding_id: str = "Qwen3-Embedding-0.6B"
    context_window: int = 4096
    max_tokens: int = 1400
    temperature: float = 0.1
    timeout: float = 180

    @field_validator("model_url", "embedding_url")
    @classmethod
    def local_only(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "http" or parsed.hostname not in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            raise ValueError(
                "Model endpoints must be local HTTP loopback addresses. Remote APIs require explicit authorization and a code change."
            )
        return value.rstrip("/")


settings = Settings()
