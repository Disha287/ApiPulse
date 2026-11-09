from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "API Pulse AI"
    DATABASE_URL: str = (
        "postgresql+asyncpg://apipulse_user:apipulse_password@localhost:5432/apipulse_db"
    )
    REDIS_URL: str = "redis://localhost:6379/0"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

