from functools import lru_cache
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)
    app_env: str = "local"
    app_name: str = "MarineOn AI Service"
    log_level: str = "INFO"
    aws_region: str = "ap-southeast-1"
    knowledge_base_id: str = ""
    model_arn: str = ""
    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")
    chat_memory_ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    chat_memory_max_qa_pairs: int = Field(default=10, ge=1, le=50)
    chat_lock_timeout_seconds: int = Field(default=180, ge=10, le=600)
    chat_lock_wait_seconds: int = Field(default=5, ge=1, le=60)
    internal_api_token: SecretStr = SecretStr("")
    max_message_chars: int = Field(default=8000, ge=1, le=50000)
    jwt_secret: SecretStr
    jwt_issuer: str
    jwt_audience: str
    java_api_base_url: str


@lru_cache
def get_settings() -> Settings:
    return Settings()
