from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration loaded from environment variables.
    """

    # ==========================================================
    # Application
    # ==========================================================

    APP_NAME: str
    APP_VERSION: str
    APP_ENV: str
    DEBUG: bool

    # ==========================================================
    # API
    # ==========================================================

    API_V1_STR: str

    # ==========================================================
    # Security
    # ==========================================================

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # ==========================================================
    # Development Database
    # ==========================================================

    DATABASE_HOST: str
    DATABASE_PORT: int
    DATABASE_NAME: str
    DATABASE_USER: str
    DATABASE_PASSWORD: str

    # ==========================================================
    # Test Database
    # ==========================================================

    TEST_DATABASE_HOST: str
    TEST_DATABASE_PORT: int
    TEST_DATABASE_NAME: str
    TEST_DATABASE_USER: str
    TEST_DATABASE_PASSWORD: str

    # ==========================================================
    # CORS
    # ==========================================================

    BACKEND_CORS_ORIGINS: str

    # ==========================================================
    # Machine Learning
    # ==========================================================

    MODEL_PATH: str

    # ==========================================================
    # Pydantic Settings
    # ==========================================================

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
    )

    # ==========================================================
    # Development Database URLs
    # ==========================================================

    @property
    def DATABASE_URL(self) -> str:
        """
        Async SQLAlchemy database URL.

        Used by:
            - FastAPI
            - Async SQLAlchemy
            - Repositories
            - Services
        """

        return (
            f"postgresql+asyncpg://"
            f"{self.DATABASE_USER}:"
            f"{self.DATABASE_PASSWORD}@"
            f"{self.DATABASE_HOST}:"
            f"{self.DATABASE_PORT}/"
            f"{self.DATABASE_NAME}"
        )

    @property
    def SYNC_DATABASE_URL(self) -> str:
        """
        Synchronous SQLAlchemy database URL.

        Used by:
            - Alembic migrations
        """

        return (
            f"postgresql+psycopg2://"
            f"{self.DATABASE_USER}:"
            f"{self.DATABASE_PASSWORD}@"
            f"{self.DATABASE_HOST}:"
            f"{self.DATABASE_PORT}/"
            f"{self.DATABASE_NAME}"
        )

    # ==========================================================
    # Test Database URLs
    # ==========================================================

    @property
    def TEST_DATABASE_URL(self) -> str:
        """
        Async SQLAlchemy database URL used exclusively
        by the automated test suite.
        """

        return (
            f"postgresql+asyncpg://"
            f"{self.TEST_DATABASE_USER}:"
            f"{self.TEST_DATABASE_PASSWORD}@"
            f"{self.TEST_DATABASE_HOST}:"
            f"{self.TEST_DATABASE_PORT}/"
            f"{self.TEST_DATABASE_NAME}"
        )

    @property
    def TEST_SYNC_DATABASE_URL(self) -> str:
        """
        Synchronous SQLAlchemy database URL for the
        automated test database.

        Can be used by Alembic or other synchronous tools
        if required.
        """

        return (
            f"postgresql+psycopg2://"
            f"{self.TEST_DATABASE_USER}:"
            f"{self.TEST_DATABASE_PASSWORD}@"
            f"{self.TEST_DATABASE_HOST}:"
            f"{self.TEST_DATABASE_PORT}/"
            f"{self.TEST_DATABASE_NAME}"
        )


@lru_cache
def get_settings() -> Settings:
    """
    Return a cached Settings instance.
    """

    return Settings()


settings = get_settings()