from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    eia_api_key: str = "DEMO_KEY"
    data_dir: str = "data/silver"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:4173"]

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
