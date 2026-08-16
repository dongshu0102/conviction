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

    # -- Interactive Brokers (real brokerage integration) --
    # Real money is at stake once configured -- see brokerage_provider.py
    # and ibkr_provider.py's own docstrings for the full safety design.
    # private_key_jwt (RFC 7523) client authentication, confirmed
    # directly against IBKR's own documentation -- not a simple API key.
    ibkr_private_key_pem: str = ""  # RSA private key, PEM format
    ibkr_client_id: str = ""
    ibkr_account_id: str = ""
    # A genuine, separate opt-in, not inferred from whichever
    # account_id happens to be configured -- must be explicitly,
    # deliberately set to true for a real order to ever be allowed to
    # reach a non-paper ("DU"-prefixed) account. Defaults to false.
    ibkr_live_trading_enabled: bool = False

    # -- Alpaca (real brokerage integration, second provider option
    # alongside IBKR) -- genuinely simpler auth than IBKR: a plain
    # API key/secret pair, confirmed directly from Alpaca's own docs.
    alpaca_api_key: str = ""
    alpaca_api_secret: str = ""
    # A genuine, separate opt-in, same principle as
    # ibkr_live_trading_enabled: must be explicitly, deliberately set
    # to true before this provider will ever point at Alpaca's real,
    # live base URL rather than the paper trading one. Defaults to
    # false.
    alpaca_live_trading_enabled: bool = False

    # -- Tradier (real brokerage integration, third provider option
    # alongside IBKR and Alpaca) -- confirmed directly against
    # Tradier's own, static documentation, giving genuinely higher
    # confidence in this specific integration's shape than in IBKR's.
    tradier_api_token: str = ""
    tradier_account_id: str = ""
    # A genuine, separate opt-in, same principle as the other two
    # providers' own live-trading flags: must be explicitly,
    # deliberately set to true before this provider will ever point
    # at Tradier's real, live base URL rather than the sandbox
    # (paper trading) one. Defaults to false.
    tradier_live_trading_enabled: bool = False

    # Which brokerage this app actually trades through -- "ibkr" or
    # "alpaca". Both providers can be fully configured at once (e.g.
    # while migrating, or testing one against the other), but only one
    # is ever active for real order placement at a time, chosen
    # explicitly here rather than inferred from which credentials
    # happen to be present.
    active_brokerage_provider: str = "ibkr"

    # -- SEC EDGAR (Form 13F bulk data sets) --
    # No API key at all -- SEC requires only a compliant User-Agent
    # identifying the requester with a real, monitored contact email,
    # confirmed directly from SEC's own fair-access policy. Requests
    # without one, or with a generic/default library User-Agent, are
    # rejected with 403. Format: "AppName contact@email".
    sec_edgar_user_agent: str = "Conviction dong.shu0102@gmail.com"

    # -- FRED (deep macro history — FMP's own economic-indicators
    # endpoint hard-caps at 2 rows regardless of plan tier, confirmed
    # directly including after upgrading to test this specifically) --
    fred_api_key: str = ""
    fred_base_url: str = "https://api.stlouisfed.org/fred"
    fred_request_timeout_seconds: float = 15.0

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
