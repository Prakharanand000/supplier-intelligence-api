"""Application configuration, loaded from environment / .env."""

from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = (
        "postgresql+asyncpg://supplier:supplier@localhost:5432/supplier_intel"
    )
    allow_sqlite_fallback: bool = True
    sqlite_url: str = f"sqlite+aiosqlite:///{(DATA_DIR / 'supplier_intel.db').as_posix()}"

    # Claude
    anthropic_api_key: str | None = None
    claude_model: str = "claude-opus-4-8"
    claude_effort: str = "high"

    # Outbound HTTP identity. SEC EDGAR rejects requests without a contact.
    user_agent: str = "SupplierIntelligenceAPI/0.1 (contact@example.com)"

    # Embeddings: auto | openai | local | hashed
    embedding_backend: str = "auto"
    openai_api_key: str | None = None

    # Optional source credentials
    courtlistener_api_token: str | None = None

    # Tuning
    http_cache_ttl_hours: int = 24
    ofac_refresh_hours: int = 24
    gdelt_months: int = 24
    investigation_timeout_seconds: int = 60

    @field_validator("database_url")
    @classmethod
    def _use_async_driver(cls, value: str) -> str:
        """Normalize managed-Postgres URLs to the async driver.

        Render, Railway, Heroku and friends inject `postgres://...`, which
        SQLAlchemy's async engine cannot open. Rewriting it here means the
        platform's own connection string works unmodified.
        """
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+asyncpg://" + value[len(prefix):]
        return value

    # Per-host request budget (requests/second). SEC caps at 10/s.
    rate_limits: dict[str, float] = {
        "www.sec.gov": 8.0,
        "data.sec.gov": 8.0,
        "efts.sec.gov": 8.0,
        "api.gleif.org": 5.0,
        # GDELT asks for no more than one request every 5 seconds and returns a
        # plain-text 429 above that; 5s exactly still trips it, so allow ~8s.
        "api.gdeltproject.org": 0.12,
        "www.courtlistener.com": 2.0,
    }


settings = Settings()
DATA_DIR.mkdir(parents=True, exist_ok=True)
