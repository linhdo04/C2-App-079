from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    deepseek_api_key: str = Field(alias="DEEPSEEK_API_KEY", default="")
    deepseek_api_base: str = Field(
        alias="DEEPSEEK_API_BASE", default="https://api.deepseek.com"
    )
    llm_provider: str = Field(alias="LLM_PROVIDER", default="deepseek")
    default_model: str = Field(alias="DEFAULT_MODEL", default="deepseek-v4-flash")
    tavily_api_key: str = Field(alias="TAVILY_API_KEY")
    langsmith_api_key: str | None = Field(alias="LANGSMITH_API_KEY", default=None)
    langsmith_endpoint: str | None = Field(alias="LANGSMITH_ENDPOINT", default=None)
    langsmith_tracing: bool = Field(alias="LANGSMITH_TRACING", default=True)
    langsmith_project: str | None = Field(alias="LANGSMITH_PROJECT", default=None)
    langsmith_workspace_id: str | None = Field(
        alias="LANGSMITH_WORKSPACE_ID", default=None
    )

    agent_tool_timeout_seconds: float = Field(
        alias="AGENT_TOOL_TIMEOUT_SECONDS", default=15.0, gt=0
    )
    agent_llm_timeout_seconds: float = Field(
        alias="AGENT_LLM_TIMEOUT_SECONDS", default=20.0, gt=0
    )
    agent_llm_max_retries: int = Field(alias="AGENT_LLM_MAX_RETRIES", default=1, ge=0)
    agent_llm_retry_backoff_seconds: float = Field(
        alias="AGENT_LLM_RETRY_BACKOFF_SECONDS", default=0.5, ge=0
    )
    agent_search_filter_enabled: bool = Field(
        alias="AGENT_SEARCH_FILTER_ENABLED", default=True
    )
    agent_search_filter_timeout_seconds: float = Field(
        alias="AGENT_SEARCH_FILTER_TIMEOUT_SECONDS", default=8.0, gt=0
    )
    agent_fallback_router_timeout_seconds: float = Field(
        alias="AGENT_FALLBACK_ROUTER_TIMEOUT_SECONDS", default=6.0, gt=0
    )
    agent_intent_router_enabled: bool = Field(
        alias="AGENT_INTENT_ROUTER_ENABLED", default=True
    )
    agent_intent_router_timeout_seconds: float = Field(
        alias="AGENT_INTENT_ROUTER_TIMEOUT_SECONDS", default=3.0, gt=0
    )
    agent_intent_router_min_confidence: float = Field(
        alias="AGENT_INTENT_ROUTER_MIN_CONFIDENCE", default=0.65, ge=0, le=1
    )
    agent_max_iterations: int = Field(alias="AGENT_MAX_ITERATIONS", default=6, gt=0)
    agent_tool_max_retries: int = Field(alias="AGENT_TOOL_MAX_RETRIES", default=1, ge=0)
    agent_tool_retry_backoff_seconds: float = Field(
        alias="AGENT_TOOL_RETRY_BACKOFF_SECONDS", default=0.25, ge=0
    )
    agent_memory_max_messages: int = Field(
        alias="AGENT_MEMORY_MAX_MESSAGES", default=10, gt=0
    )
    agent_memory_max_characters: int = Field(
        alias="AGENT_MEMORY_MAX_CHARACTERS", default=12_000, gt=0
    )
    agent_guardrails_enabled: bool = Field(
        alias="AGENT_GUARDRAILS_ENABLED", default=True
    )
    agent_guardrails_redact_pii: bool = Field(
        alias="AGENT_GUARDRAILS_REDACT_PII", default=True
    )
    agent_guardrails_block_secrets: bool = Field(
        alias="AGENT_GUARDRAILS_BLOCK_SECRETS", default=True
    )
    agent_guardrails_block_prompt_injection: bool = Field(
        alias="AGENT_GUARDRAILS_BLOCK_PROMPT_INJECTION", default=True
    )
    agent_checkpointing_enabled: bool = Field(
        alias="AGENT_CHECKPOINTING_ENABLED", default=True
    )
    agent_checkpoint_durability: Literal["sync", "async", "exit"] = Field(
        alias="AGENT_CHECKPOINT_DURABILITY", default="sync"
    )
    langgraph_checkpoint_setup_on_start: bool = Field(
        alias="LANGGRAPH_CHECKPOINT_SETUP_ON_START", default=True
    )

    app_name: str = Field(alias="APP_NAME", default="Autonomous Drones")
    app_domain: str = Field(alias="APP_DOMAIN", default="127.0.0.1")
    app_env: Literal["development", "production", "testing", "local"] = Field(
        alias="APP_ENV", default="production"
    )
    app_debug: bool = Field(alias="APP_DEBUG", default=False)
    frontend_origin: str = Field(
        alias="FRONTEND_ORIGIN", default="http://127.0.0.1:3000"
    )

    api_host: str = Field(alias="API_HOST", default="0.0.0.0")
    api_port: int = Field(alias="API_PORT", default=8000)
    api_prefix: str = Field(alias="API_PREFIX", default="/api")

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        alias="LOG_LEVEL", default="INFO"
    )

    postgres_user: str = Field(alias="POSTGRES_USER", default="postgres")
    postgres_password: str = Field(alias="POSTGRES_PASSWORD", default="postgres")
    postgres_db: str = Field(alias="POSTGRES_DB", default="autonomous_drones")
    postgres_port: int = Field(alias="POSTGRES_PORT", default=5432)
    postgres_host: str = Field(alias="POSTGRES_HOST", default="127.0.0.1")

    redis_host: str = Field(alias="REDIS_HOST", default="127.0.0.1")
    redis_port: int = Field(alias="REDIS_PORT", default=6379)
    redis_user: str | None = Field(alias="REDIS_USER", default=None)
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
        if self.redis_password:
            if self.redis_user:
                return f"redis://{self.redis_user}:{self.redis_password}@{self.redis_host}:{self.redis_port}"
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}"
        return f"redis://{self.redis_host}:{self.redis_port}"

    @property
    def frontend_origins(self) -> list[str]:
        return [
            origin.strip().rstrip("/")
            for origin in self.frontend_origin.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
