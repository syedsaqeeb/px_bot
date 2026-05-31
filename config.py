"""
PSX Trading Bot - Configuration
Loads settings from environment variables / .env file.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Central configuration loaded from environment."""

    # --- Authentication ---
    BOT_USERNAME: str = os.getenv("BOT_USERNAME", "admin")
    BOT_PASSWORD: str = os.getenv("BOT_PASSWORD", "changeme")
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "dev-secret-change-in-production")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))

    # --- Data ---
    DATA_CACHE_DIR: str = os.getenv("DATA_CACHE_DIR", "./data_cache")
    HISTORY_YEARS: int = int(os.getenv("HISTORY_YEARS", "3"))

    # --- SBP Monetary Policy ---
    SBP_POLICY_RATE: float = float(os.getenv("SBP_POLICY_RATE", "11.50"))
    SBP_LAST_UPDATE: str = os.getenv("SBP_LAST_UPDATE", "2026-04-27")

    # --- Server ---
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # --- Constants ---
    PSX_MARKET_OPEN = "09:30"          # PKT
    PSX_MARKET_CLOSE = "15:30"         # PKT
    TIMEZONE = "Asia/Karachi"

    # Scoring weights
    MATH_WEIGHT: float = 0.50
    SENTIMENT_WEIGHT: float = 0.25
    VALUE_WEIGHT: float = 0.25

    # Z-score thresholds
    ENTRY_Z: float = -2.0              # Buy signal: 2 std devs below mean
    EXIT_Z: float = 0.0                # Sell signal: price reverts to mean
    STOP_Z: float = -3.5               # Hard stop-loss threshold


settings = Settings()
Path(settings.DATA_CACHE_DIR).mkdir(parents=True, exist_ok=True)
