"""Application settings, read from environment variables or the .env file"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    max_booking_hours: int = 8
    cors_origins: list[str] = []

    admin_email: str | None = None
    admin_password: str | None = None


settings = Settings()
