from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: str = Field(alias="GEMINI_API_KEY")
    tavily_api_key: str = Field(alias="TAVILY_API_KEY")
    agent_tool_timeout_seconds: float = Field(
        alias="AGENT_TOOL_TIMEOUT_SECONDS",
        default=15.0,
        gt=0,
    )
    agent_llm_timeout_seconds: float = Field(
        alias="AGENT_LLM_TIMEOUT_SECONDS",
        default=20.0,
        gt=0,
    )

    app_name: str = Field(alias="APP_NAME")
    app_env: Literal["development", "production", "testing"] = Field(
        alias="APP_ENV", default="production"
    )
    app_debug: bool = Field(alias="APP_DEBUG", default=False)
    frontend_origin: str = Field(
        alias="FRONTEND_ORIGIN", default="http://localhost:3000"
    )

    api_host: str = Field(alias="API_HOST")
    api_port: int = Field(alias="API_PORT")
    api_prefix: str = Field(alias="API_PREFIX")

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        alias="LOG_LEVEL", default="INFO"
    )

    postgres_user: str = Field(alias="POSTGRES_USER")
    postgres_password: str = Field(alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(alias="POSTGRES_DB")
    postgres_port: int = Field(alias="POSTGRES_PORT")
    postgres_host: str = Field(alias="POSTGRES_HOST")

    redis_host: str = Field(alias="REDIS_HOST")
    redis_port: int = Field(alias="REDIS_PORT")
    redis_password: str | None = Field(alias="REDIS_PASSWORD", default=None)

    jwt_secret_key: str = Field(alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(alias="JWT_ALGORITHM", default="HS256")
    access_token_expire_minutes: int = Field(
        alias="ACCESS_TOKEN_EXPIRE_MINUTES", default=60
    )
    refresh_token_expire_days: int = Field(
        alias="REFRESH_TOKEN_EXPIRE_DAYS", default=30
    )

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:"
            f"{self.postgres_password}@"
            f"{self.postgres_host}:"
            f"{self.postgres_port}/"
            f"{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}"

    @property
    def frontend_origins(self) -> list[str]:
        return [
            origin.strip().rstrip("/")
            for origin in self.frontend_origin.split(",")
            if origin.strip()
        ]


settings = Settings()  # type: ignore[call-arg]
