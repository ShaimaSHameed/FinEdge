from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False
    )

    NEWS_API_KEY: str
    OPENROUTER_API_KEY: str
    ALPACA_API_KEY: str | None = None
    ALPACA_SECRET_KEY: str | None = None
    ALPACA_API_SECRET: str | None = None
    APCA_API_KEY_ID: str | None = None
    APCA_API_SECRET_KEY: str | None = None
    ALPACA_DATA_URL: str = "https://data.alpaca.markets"
    ALPACA_STOCK_FEED: str = "iex"
    EODHD_API_KEY: str | None = None
    EODHD_BASE_URL: str = "https://eodhd.com/api"
    FUNDAMENTAL_ARTIFACT_DIR: str = "/app/artifacts/fundamental"
    FUNDAMENTAL_REQUIRE_MODEL_SIGNAL: bool = True
    FUNDAMENTAL_ANALYSIS_CACHE_HOURS: int = 24
    FUNDAMENTAL_REPORT_CACHE_DAYS: int = 7
    SENTIMENTAL_ARTIFACT_DIR: str = "/artifacts/sentimental"
    SENTIMENTAL_REQUIRE_MODEL_ARTIFACT: bool = True
    SENTIMENTAL_DEFAULT_MODEL: str = "gemini31_pro"
    SENTIMENTAL_MAX_ARTIFACT_AGE_HOURS: int = 72
    SENTIMENTAL_ALLOW_LIVE_FALLBACK: bool = True
    TECHNICAL_ARTIFACT_DIR: str = "/artifacts/technical/final_1d_artifacts"
    TECHNICAL_INTRADAY_ARTIFACT_DIR: str = "/artifacts/technical/final_artifacts"
    TECHNICAL_REQUIRE_MODEL_ARTIFACT: bool = True
    TECHNICAL_REQUIRE_ALPACA_LIVE_DATA: bool = True
    TECHNICAL_INFERENCE_WARMUP_BARS: int = 420
    TECHNICAL_INTRADAY_WARMUP_BARS: int = 390
    TECHNICAL_TARGET_SCALE_FLOOR: float = 0.003
    TECHNICAL_TARGET_SCALE_CEILING: float = 0.08
    LLM_MODEL: str = "google/gemini-3-flash-preview"
    EMAIL_FROM: str = ""
    EMAIL_PASSWORD: str = ""
    DATABASE_URL: str
    SECRET_KEY: str = "change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15


settings = Settings()
