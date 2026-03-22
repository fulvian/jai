"""Configuration settings for PersAn."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # Me4BrAIn connection
    me4brain_url: str = "http://localhost:8000"  # Docker Me4BrAIn API port
    me4brain_api_key: str = ""
    me4brain_timeout: float = 600.0  # 10 minutes for complex queries

    # Backend server
    persan_port: int = 8888
    persan_host: str = "0.0.0.0"
    debug: bool = True

    # Authentication (predisposto, disabilitato in dev)
    auth_enabled: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignora variabili frontend (NEXT_PUBLIC_*)


settings = Settings()
