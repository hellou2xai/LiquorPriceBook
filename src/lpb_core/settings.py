"""Application settings, sourced from environment variables.

Render injects DATABASE_URL and any custom env vars declared in render.yaml.
For local dev, populate a .env file (not committed). Anything secret stays in
the Render dashboard with sync=false in render.yaml.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ----- core -----
    app_env: str = Field(default="development", alias="APP_ENV")
    app_domain: str = Field(default="liquorpricebook.com", alias="APP_DOMAIN")
    web_origin: str = Field(default="http://localhost:5173", alias="WEB_ORIGIN")

    # ----- database -----
    database_url: str = Field(
        default="postgresql+psycopg://lpb:lpb@localhost:5432/liquorpricebook",
        alias="DATABASE_URL",
    )

    # ----- clerk auth -----
    clerk_publishable_key: str | None = Field(default=None, alias="CLERK_PUBLISHABLE_KEY")
    clerk_secret_key: str | None = Field(default=None, alias="CLERK_SECRET_KEY")
    clerk_jwt_issuer: str | None = Field(default=None, alias="CLERK_JWT_ISSUER")

    # ----- AI -----
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")

    # ----- email -----
    resend_api_key: str | None = Field(default=None, alias="RESEND_API_KEY")

    # ----- observability -----
    sentry_dsn: str | None = Field(default=None, alias="SENTRY_DSN")

    # ----- worker -----
    pdf_storage_path: Path = Field(
        default=Path("./var/data/pdfs"), alias="PDF_STORAGE_PATH"
    )

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def database_url_sync(self) -> str:
        """Same URL but with the psycopg sync driver, for Alembic."""
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
