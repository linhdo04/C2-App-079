from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(alias="APP_NAME")
    app_env: Literal["development", "production", "testing"] = Field(
        alias="APP_ENV", default="production"
    )
    app_debug: bool = Field(alias="APP_DEBUG", default=False)

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


settings = Settings()  # type: ignore[call-arg]
