"""Centralized, typed configuration. No module anywhere else reads
os.environ directly — settings flow from here so there's exactly one
place that knows about env var names and defaults.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # -- Database --
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/conviction"

    # -- Financial Modeling Prep --
    fmp_api_key: str = ""
    # FMP deprecated the path-based /api/v3/ endpoints (they now 403) in favor
    # of query-param-based /stable/ endpoints. See fmp_provider.py.
    fmp_base_url: str = "https://financialmodelingprep.com/stable"
    fmp_request_timeout_seconds: float = 15.0

    # -- Anthropic (Company Research Agent) --
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    anthropic_max_tokens: int = 2000

    # -- MarketData.app (options data) --
    marketdata_api_key: str = ""

    # -- Email (AWS SES) --
    # Must be a verified SES identity or the send fails — see
    # ses_email_sender.py's docstring for the sandbox-mode caveat.
    ses_sender_email: str = "noreply@conviction.example.com"
    ses_aws_region: str = "us-east-1"
    # Used to build the password-reset link embedded in the email.
    frontend_base_url: str = "https://www.firstagentteam.com"

    # -- Admin bootstrap --
    # Safe to leave set permanently — idempotent, only ever ensures
    # THIS specific pre-configured email has the admin role, never
    # grants it to anyone else, never demotes anyone. The only way to
    # get a first admin at all without direct database access.
    bootstrap_admin_email: str = ""

    # -- App --
    environment: str = "development"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
