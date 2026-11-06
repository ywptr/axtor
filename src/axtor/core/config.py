from typing import Literal

from pydantic import Field, PostgresDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AXTOR_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: PostgresDsn
    db_pool_size: int = Field(default=5, ge=1, le=100)
    db_max_overflow: int = Field(default=5, ge=0, le=100)
    db_timeout_seconds: float = Field(default=3, gt=0, le=30)

    @model_validator(mode="after")
    def validate_database(self) -> "Settings":
        if self.database_url.scheme != "postgresql+asyncpg":
            raise ValueError("database_url must use postgresql+asyncpg")
        if not self.database_url.path or self.database_url.path == "/":
            raise ValueError("database_url must specify a database")
        return self
