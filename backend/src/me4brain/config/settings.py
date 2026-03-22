"""Me4BrAIn Settings - Pydantic Configuration Management.

Gestisce tutte le configurazioni del sistema con validazione tipizzata.
Supporta environment variables e file .env.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root directory (where .env file is located)
# This file is at: src/me4brain/config/settings.py
# Project root is 4 levels up
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
ENV_FILE_PATH = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Configurazione globale Me4BrAIn Core."""

    model_config = SettingsConfigDict(
        env_prefix="ME4BRAIN_",
        # Use absolute path to .env to avoid working directory issues
        env_file=str(ENV_FILE_PATH) if ENV_FILE_PATH.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # API Configuration
    # -------------------------------------------------------------------------
    host: str = Field(default="0.0.0.0", description="API host")
    port: int = Field(default=8089, description="API port")
    debug: bool = Field(default=False, description="Debug mode")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")
    cors_origins: str = Field(
        default="", description="Comma-separated CORS origins (empty = none in production)"
    )

    # -------------------------------------------------------------------------
    # PostgreSQL (LangGraph Checkpointing)
    # -------------------------------------------------------------------------
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_user: str = Field(default="me4brain", alias="POSTGRES_USER")
    postgres_password: SecretStr = Field(
        default=SecretStr("me4brain_secret_change_me"), alias="POSTGRES_PASSWORD"
    )
    postgres_db: str = Field(default="me4brain", alias="POSTGRES_DB")

    @property
    def postgres_dsn(self) -> str:
        """Connection string PostgreSQL."""
        return (
            f"postgresql://{self.postgres_user}:"
            f"{self.postgres_password.get_secret_value()}@"
            f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # -------------------------------------------------------------------------
    # Redis (Working Memory)
    # -------------------------------------------------------------------------
    redis_host: str = Field(default="localhost", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")
    redis_password: SecretStr | None = Field(default=None, alias="REDIS_PASSWORD")

    @property
    def redis_url(self) -> str:
        """Connection URL Redis."""
        if self.redis_password:
            return f"redis://:{self.redis_password.get_secret_value()}@{self.redis_host}:{self.redis_port}"
        return f"redis://{self.redis_host}:{self.redis_port}"

    # -------------------------------------------------------------------------
    # Qdrant (Vector Store)
    # -------------------------------------------------------------------------
    qdrant_host: str = Field(default="localhost", alias="QDRANT_HOST")
    qdrant_grpc_port: int = Field(default=6334, alias="QDRANT_GRPC_PORT")
    qdrant_http_port: int = Field(default=6333, alias="QDRANT_HTTP_PORT")

    # -------------------------------------------------------------------------
    # Neo4j (Graph Database Secondary)
    # -------------------------------------------------------------------------
    neo4j_host: str = Field(default="localhost", alias="NEO4J_HOST")
    neo4j_http_port: int = Field(default=7474, alias="NEO4J_HTTP_PORT")
    neo4j_bolt_port: int = Field(default=7687, alias="NEO4J_BOLT_PORT")
    neo4j_user: str = Field(default="neo4j", alias="NEO4J_USER")
    neo4j_password: SecretStr = Field(
        default=SecretStr("neo4j_secret_change_me"), alias="NEO4J_PASSWORD"
    )

    @property
    def neo4j_uri(self) -> str:
        """Connection URI Neo4j Bolt."""
        return f"bolt://{self.neo4j_host}:{self.neo4j_bolt_port}"

    # -------------------------------------------------------------------------
    # Keycloak (Authentication)
    # -------------------------------------------------------------------------
    keycloak_url: str = Field(default="http://localhost:8489", alias="KEYCLOAK_URL")
    keycloak_realm: str = Field(default="me4brain", alias="KEYCLOAK_REALM")
    keycloak_client_id: str = Field(default="me4brain-api", alias="KEYCLOAK_CLIENT_ID")
    keycloak_client_secret: SecretStr = Field(
        default=SecretStr("change_me_in_production"), alias="KEYCLOAK_CLIENT_SECRET"
    )

    # -------------------------------------------------------------------------
    # LLM Providers
    # -------------------------------------------------------------------------
    llm_primary_provider: Literal["openai", "anthropic", "google"] = Field(
        default="openai", alias="LLM_PRIMARY_PROVIDER"
    )
    llm_primary_model: str = Field(default="gpt-4o", alias="LLM_PRIMARY_MODEL")
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")

    llm_secondary_provider: Literal["openai", "anthropic", "google"] = Field(
        default="google", alias="LLM_SECONDARY_PROVIDER"
    )
    llm_secondary_model: str = Field(default="gemini-1.5-flash", alias="LLM_SECONDARY_MODEL")
    google_api_key: SecretStr | None = Field(default=None, alias="GOOGLE_API_KEY")

    # -------------------------------------------------------------------------
    # Embedding Model
    # -------------------------------------------------------------------------
    embedding_model: str = Field(default="BAAI/bge-m3", alias="EMBEDDING_MODEL")
    embedding_device: Literal["mps", "cuda", "cpu"] = Field(default="mps", alias="EMBEDDING_DEVICE")

    # -------------------------------------------------------------------------
    # Multi-Tenancy
    # -------------------------------------------------------------------------
    default_tenant_id: str = Field(default="me4brain_core", alias="DEFAULT_TENANT_ID")
    tenant_isolation_mode: Literal["payload_filter", "collection_per_tenant"] = Field(
        default="payload_filter", alias="TENANT_ISOLATION_MODE"
    )

    # -------------------------------------------------------------------------
    # API Key Authentication (Semplice, per integrazioni locali)
    # -------------------------------------------------------------------------
    api_key: SecretStr | None = Field(default=None, alias="ME4BRAIN_API_KEY")
    api_key_header: str = Field(default="X-API-Key", alias="ME4BRAIN_API_KEY_HEADER")

    @field_validator("embedding_device", mode="before")
    @classmethod
    def validate_embedding_device(cls, v: str) -> str:
        """Fallback a CPU se MPS/CUDA non disponibili."""
        import torch

        if v == "mps" and not torch.backends.mps.is_available():
            return "cpu"
        if v == "cuda" and not torch.cuda.is_available():
            return "cpu"
        return v


@lru_cache
def get_settings() -> Settings:
    """Singleton per le settings - cached."""
    return Settings()
