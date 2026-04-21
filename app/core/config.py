from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Incident Management API"
    environment: str = "development"
    secret_key: str = "change-me"
    access_token_expire_minutes: int = 120
    database_url: str = "sqlite:///./data/incidents.db"
    redis_url: str = "redis://localhost:6379/0"
    celery_task_always_eager: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

