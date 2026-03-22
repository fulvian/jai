"""SDK Configuration using Pydantic BaseSettings."""

from pydantic_settings import BaseSettings


class Me4BrAInConfig(BaseSettings):
    """Configuration for Me4BrAIn SDK.

    Can be configured via environment variables with ME4BRAIN_ prefix.
    """

    base_url: str = "http://localhost:8089/api/v1"
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0
    tenant_id: str = "default"
    api_key: str | None = None

    model_config = {"env_prefix": "ME4BRAIN_"}
