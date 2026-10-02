"""Application configuration - fully offline, no cloud dependencies."""
from pydantic_settings import BaseSettings
from functools import lru_cache
from enum import Enum


class BusinessMode(str, Enum):
    RESTAURANT = "restaurant"
    RETAIL = "retail"
    PHARMACY = "pharmacy"
    GROCERY = "grocery"


class Settings(BaseSettings):
    APP_NAME: str = "SME POS & Business Manager"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # SQLite - 100% local
    DATABASE_URL: str = "sqlite+aiosqlite:///./pos_data.db"

    # Default business mode (can be switched at runtime via settings)
    DEFAULT_BUSINESS_MODE: BusinessMode = BusinessMode.RETAIL

    # Tax / VAT (Ethiopia standard rate example)
    DEFAULT_VAT_RATE: float = 0.15  # 15%

    # Currency
    CURRENCY_CODE: str = "ETB"
    CURRENCY_SYMBOL: str = "Br"

    # Offline sync
    OFFLINE_QUEUE_ENABLED: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()
