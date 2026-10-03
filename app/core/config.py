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

    # Google Sheets
    GOOGLE_SHEET_ID: str = ""          # put your Sheet ID here
    GOOGLE_CREDENTIALS_FILE: str = "service_account.json"  # path to the JSON key

    DEFAULT_BUSINESS_MODE: BusinessMode = BusinessMode.RETAIL
    DEFAULT_VAT_RATE: float = 0.15
    CURRENCY_CODE: str = "ETB"
    CURRENCY_SYMBOL: str = "Br"

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()
