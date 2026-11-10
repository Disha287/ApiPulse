from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "API Pulse AI"
    DATABASE_URL: str = (
        "postgresql+asyncpg://apipulse_user:apipulse_password@localhost:5432/apipulse_db"
    )
    REDIS_URL: str = "redis://localhost:6379/0"
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

