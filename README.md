# Conviction — AI Financial Intelligence Platform

An AI-native financial platform for individual investors: real S&P 500
data, deterministic financial computation where correctness matters, and
an LLM layer for synthesis, conversation, and action — grounded in that
data, never guessing at numbers it should have looked up.

Live at **https://p8xpcshdn9.us-east-1.awsapprunner.com** (API) and
**https://www.firstagentteam.com** (web app) — see
`frontend/` for the web app and `mcp_server/` for the Claude
Desktop/claude.ai integration.

## What's built

This platform implements the full professional investment workflow —
Universe → Watchlist → Screen → Research → Factor Score → Value → Risk
→ Construct → Monitor → Review — end to end, with one deliberate gap
(Execution/order routing, a different trust category entirely, out of
scope by design).

**Data foundation** — 503+ S&P 500 companies and any ingested ETF,
from Financial Modeling Prep (profile + 5 years of annual statements),
stored with a typed-fields-plus-raw-JSON schema so no vendor data is
ever silently dropped.

**AI-suggested themes** — grounded in real, live general market news
(not symbol-specific), proposes a candidate theme name, rationale, and
shortlist of tickers — some possibly not yet ingested, honestly
flagged as such. Deliberately a SUGGESTION, never an autonomous action:
creating the theme and tagging tickers still goes through the existing
human-confirmed tools. A hallucinated ticker is structurally
self-correcting — it would simply fail a real ingestion attempt, not
silently enter the system.

**Curated investment universe** — global, shared themes ("AI
Infrastructure," "China," etc.) as a many-to-many tag on top of
`Company`, not a separate parallel system. Screening and factor
rankings can scope to a theme directly.

**Cross-sectional factor scoring** — Value, Quality, Growth, Momentum,
Size, each standardized (z-scored) against the live S&P 500 universe,
not fixed bands — genuinely different from the screener below. Cached
(the full universe refresh is expensive — 500+ tickers, hundreds of
API calls) with a 24-hour staleness window, retry-with-backoff on
transient failures, and a hard split between permanent failures (a
delisted or un-ingested ticker — never retried) and transient ones (a
429 — retried with exponential backoff). Value/Size are sign-flipped
so a positive z-score always means "attractive" uniformly.

**Stock screening** — value/quality composite scoring against a
caller-named, bounded ticker list (≤15) or an entire curated theme
(≤40) — deliberately distinct scoring philosophy from factor scoring
(fixed absolute bands, not universe-relative).

**Thematic AI research synthesis** — a narrative across an entire
theme's members (common threads, divergences, risks), grounded in real
screening + factor data, never persisted (cheap to regenerate,
would go stale as a stored artifact). Explicitly warns the model about
the screen-score/factor-score polarity difference in its own prompt —
the single easiest way to accidentally invert a "good" and "bad" score.

**Real portfolio risk analysis** — concentration (HHI), sector
exposure, weighted leverage, plus actual volatility/correlation/95%
1-day parametric VaR computed from live 60-day price history. Every
volatility figure is honestly scoped (`volatility_covered_weight`) —
a ticker with too little history is excluded, never force-fit.

**Risk-parity portfolio construction** — proposes a from-scratch
dollar allocation across a list of tickers, sized purely by inverse
volatility (lower vol → more capital). Deliberately NOT mean-variance
optimization — that needs an expected-return forecast, and there's no
reliable source for one, so it isn't faked.

**Options subsystem** — Greeks, P&L, delta hedging suggestions via
MarketData.app, mixed into the same portfolios as equities.

**Continuous monitoring** — price-move alerts, entry-target alerts
(per-ticker custom thresholds), and earnings-date alerts (deduped
against existing alerts so a 15-minute cron doesn't re-fire on the
same event dozens of times a day), via a standalone cron-invoked
script — deliberately not an in-process scheduler (a real multi-worker
race condition earlier in development — see `Dockerfile` comments).

**Daily Brief** — an AI narrative synthesizing watchlist moves,
portfolio performance, and alerts, grounded in the same structured
data a person could otherwise read directly.

**ETF support** — modeled as a variant of `Company` (`asset_type`
flag), not a parallel system, so ETFs participate in watchlists,
themes, and screening for free. Value/Quality/Growth factor scores are
always `null` for a fund — not a data gap, genuinely not applicable
(no income statement to compute them from) — while Momentum and Size
(via AUM) work normally.

**Real authentication** — email/password signup and login
(`POST /auth/signup`, `POST /auth/login`), bcrypt-hashed passwords,
both producing a genuine API key rather than a separate session
mechanism — deliberately, so nothing else in the system (36 chat
tools, MCP, every existing REST endpoint) needed to change at all.
API keys themselves stay SHA-256 hashed (correct for high-entropy
random tokens — a different threat model than human-chosen passwords,
which is exactly why they use bcrypt instead). Creating an
*additional* key now requires already holding a valid one — the first
key for any identity only ever comes from a real, password-verified
signup, closing a real gap where anyone could previously mint a key
for any `user_id` string with zero proof of ownership. Every
portfolio-scoped endpoint still enforces ownership checks on top of
this — authentication proves who you are, these checks enforce what
you're allowed to touch.

**Chat agent** — 36 tools via Anthropic's tool-use API, streamed to
the frontend through the Vercel AI SDK. Deterministic computation
stays deterministic even inside the chat — share counts, Greeks,
factor composites, and risk-parity weights are all computed by plain
use cases, never estimated by the model. The system prompt is
unusually explicit about sign conventions and scoring polarity —
several real bugs this session were the *model's own narration*
inverting a correctly-computed number, not the math itself.

**Web frontend** — Next.js, "Refined Terminal" dark design. `/terminal`
(watchlist triage, news, upcoming earnings), `/universe` (theme
management, factor rankings, AI synthesis, risk-parity allocator, ETF
ingestion), and per-portfolio risk analysis — all built on top of the
REST API, not duplicating the chat agent's logic.

**MCP server** — 57 tools for Claude Desktop / claude.ai. Previously
had a real gap — options (Greeks, hedging, option holdings),
`screen_stocks`, `recommend_stocks`, `suggest_rebalancing`, and
watchlist named-list management had no REST endpoint for MCP to proxy
at all. Closed by adding 11 new REST endpoints for those exact
capabilities (`/portfolios/{id}/options/*`, `/companies/screen`,
`/portfolios/{id}/recommendations`, `/portfolios/{id}/rebalance-suggestion`,
`/watchlist/lists`, `PATCH /watchlist/{ticker}`, `/companies/{ticker}/news`),
then MCP tools proxying each — the same thin-HTTP-client pattern as
everything else here, not a reimplementation.

## Architecture

**Clean Architecture, four layers, strict dependency direction (inward only):**

```
src/
├── domain/           # Entities + repository interfaces. Zero external deps.
│   └── services/       # Pure math (z-scoring, portfolio risk, factor composites)
├── application/       # Use cases + provider/agent interfaces. Framework-free.
│   ├── use_cases/      # One class per business operation
│   └── interfaces/     # FinancialDataProvider, ResearchGenerator, ChatAgent, ...
├── infrastructure/    # Concrete implementations of the above interfaces.
│   ├── data_providers/ # FMP + MarketData.app adapters, pure parsing modules
│   ├── llm_providers/  # Anthropic adapters — research, brief, chat, synthesis
│   └── persistence/    # SQLAlchemy models + repository implementations
└── api/                # FastAPI — routers, Pydantic schemas, DI wiring

frontend/               # Next.js web app (separate deployable, own Dockerfile)
mcp_server/              # MCP server for Claude Desktop (separate deployable, STALE)
scripts/                 # Bulk ingestion, monitoring cron, factor snapshot refresh cron
```

**Dependency rule**: `domain` knows nothing about the other three layers.
`application` knows about `domain` only. `infrastructure` and `api` depend
inward. The interface (`FinancialDataProvider`, `ChatAgent`, etc.) is the
seam — a provider's specific wire format never leaks past its adapter.

**Optional provider capabilities** (news, price history, earnings
calendar, ETF profiles) are non-abstract methods on `FinancialDataProvider`
that raise `NotImplementedError` by default, checked via `hasattr` at
call sites — lets a capability be added without touching every existing
fake/test provider, and every consumer degrades honestly (a `None`
signal, not a crash) when a provider doesn't support it.

## Local setup

### Backend

```bash
cp .env.example .env   # set FMP_API_KEY, ANTHROPIC_API_KEY, DATABASE_URL, MARKETDATA_API_KEY
pip install -r requirements.txt
brew services start postgresql@16   # or your local Postgres
alembic upgrade head
uvicorn src.api.main:app --reload
```

API docs: http://localhost:8000/docs

### Frontend

```bash
cd frontend
cp .env.local.example .env.local   # points at localhost:8000 instead of production
npm install
npm run dev
```

**Restart the dev server after any `.env.local` change** — Next.js only
reads it at startup, not on hot-reload.

### MCP server (Claude Desktop / claude.ai)

See `mcp_server/README.md` for setup. At parity with the chat agent
for everything with a REST endpoint (see "What's built" above for the
handful of chat-only exceptions).

## Try it

```bash
# Ingest a company
curl -X POST "http://localhost:8000/companies/AAPL/ingest?years=5"

# Ingest an ETF (separate path — no financial statements to fetch)
curl -X POST "http://localhost:8000/companies/SPY/ingest-etf"

# Sign up (real email + password now — this is the actual account creation step)
curl -X POST "http://localhost:8000/auth/signup" \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "yourpassword"}'
# Returns a plaintext_key — save it, shown exactly once

# Everything else needs that key
curl "http://localhost:8000/companies/AAPL/factor-score" -H "X-Api-Key: fi_live_..."
curl -X POST "http://localhost:8000/universe/themes/AI%20Infrastructure" -H "X-Api-Key: fi_live_..."
curl -X POST "http://localhost:8000/chat" -H "X-Api-Key: fi_live_..." \
  -H "Content-Type: application/json" \
  -d '{"message": "synthesize my AI Infrastructure theme", "history": []}'
```

## Bootstrapping the first admin

`/admin/*` endpoints (factor-snapshot refresh, non-USD-reporter audit,
user role management) require a real `admin` role, not just a valid
API key — but every account starts as `user`, including the very
first one, since there's deliberately no self-promotion endpoint (that
would defeat the whole point).

To get a first admin:
1. Sign up normally (`POST /auth/signup`) with the email you want as admin.
2. Set the `BOOTSTRAP_ADMIN_EMAIL` environment variable to that same
   (normalized, lowercase) email.
3. Redeploy. On every startup, if that email matches an existing
   account, it's promoted to admin — idempotent, safe to leave
   configured permanently, never touches any other account.
4. From there, that admin can promote others via
   `PATCH /admin/users/{user_id}/role` — no need to keep touching the
   environment variable for every subsequent admin.

## Tests

```bash
pytest tests/ -v
```

240 tests, all against in-memory fakes (`tests/unit/fakes.py`) — no
database, no network, no mocking framework. If a repository or agent
interface changes shape, the fakes fail to implement it and the suite
fails to even collect, catching the break at the earliest possible
point. Every real production bug caught this session got a regression
test using the actual numbers involved (e.g. TSM's real TWD-denominated
EPS, not a synthetic example) — see `test_compute_valuation.py`'s
currency-guard tests for the pattern.

**Frontend and MCP server now have automated tests** (`frontend/lib/api.test.ts`,
`frontend/components/LedgerRow.test.tsx`, `mcp_server/tests/test_server.py`)
— but **none of them have actually been run**. This sandbox has no
PyPI or npm registry access at all, so `httpx`, `pytest-asyncio`,
`vitest`, and `@testing-library/react` could never be installed here
to execute anything. Written carefully against known-correct
conventions, focused especially on the exact request-shape bugs that
were real, confirmed production issues this session (e.g. `vitest run`
should include a dedicated test proving `constructRiskParity` sends a
JSON body, not query params — the precise thing that broke live
earlier). Run `npm test` (frontend) and `pip install -r
requirements-dev.txt && pytest` (`mcp_server/`) to get the real,
first-ever verification.

## Database migrations

```bash
alembic upgrade head         # apply all pending migrations
alembic revision -m "add X"  # create a new empty migration to edit by hand
alembic downgrade -1         # roll back one migration
```

12 migrations as of this writing (`0001` baseline through `0012` ETF
support).

## Deployment (production)

AWS: RDS Postgres (private, `PubliclyAccessible: false` — genuinely no
route from outside AWS, by design), ECR, App Runner (backend + separate
frontend service), Secrets Manager, EventBridge Scheduler (daily factor
snapshot refresh), GitHub Actions OIDC (no long-lived AWS credentials
in CI). The backend's VPC connector lives on a dedicated private subnet
routed through a NAT Gateway to a *separate* public subnet — an earlier
attempt that put the NAT Gateway in the same subnet it was supposed to
route for caused a real routing loop that took a full debugging session
to trace via CloudTrail. The frontend needs no VPC connector at all —
it only calls the public API over HTTPS.

### Hard-won operational lessons

These cost real debugging time and are exactly the kind of thing that's
easy to re-discover the hard way if this list doesn't exist:

- **`aws apprunner wait ...` does not exist.** App Runner has no CLI
  waiters defined at all (only some services, like EC2, ship them).
  Poll `describe-service` in a loop instead — see
  `.github/workflows/deploy-frontend.yml`.
- **`update-service` diffs the JSON config text, not the image digest.**
  If the source configuration is byte-identical to the last deploy
  (same tag, same env vars — the normal case), App Runner treats it as
  "no change" and silently skips pulling the new image, even though
  the call returns success. Confirmed in production: months of deploys
  were no-ops. Always follow `update-service` with an explicit
  `start-deployment` if the image itself changed.
- **`iam:PassRole` conditions can silently never match.** A policy
  conditioned on `iam:PassedToService` can report "allowed" from
  `simulate-principal-policy` (which lets you assert any hypothetical
  context value) while the real API call never actually populates that
  context key — so the live call denies anyway. If simulation says
  allowed but the real call still 403s, suspect the condition itself,
  not the resource/action.
- **A private RDS instance has no route from a local machine, ever** —
  not a security-group fix, a fundamentally different network path.
  Maintenance operations (factor snapshot refresh, etc.) that need DB
  access run as backend-triggered admin endpoints
  (`POST /admin/refresh-factor-snapshot`), executed as a
  `BackgroundTask` so the HTTP response doesn't block on a multi-minute
  job — not from a local script.
- **Postgres silently strips timezone info on a plain `timestamp`
  column.** A value saved with `datetime.now(timezone.utc)` comes back
  *naive* on read, even though nothing about the write looked wrong.
  Any arithmetic against a fresh `datetime.now(timezone.utc)` then
  raises `TypeError: can't subtract offset-naive and offset-aware
  datetimes` — invisible in tests using in-memory fakes, since those
  never round-trip through real Postgres. Fixed by normalizing to UTC
  at the repository boundary (see `factor_score_repository_impl.py`).
- **Mixing a USD price with a non-USD financial statement produces a
  number, not an error.** TSM reports in TWD; its USD ADR price
  divided by its TWD EPS produced a P/E of ~1.2 — arithmetically valid,
  completely meaningless, and screening ranked it #1 cheapest in the
  S&P 500 on the strength of it. `ComputeValuationUseCase` now checks
  `reported_currency` and returns `None` rather than a wrong number for
  any ratio that mixes currencies.
- **FastAPI's default parameter binding for `list[str]` is a JSON
  body, not repeated query params** — the opposite of what feels
  intuitive. A bare `list[str]` function parameter (no `Query()`/
  `Body()` annotation) expects `{"field": [...]}` in the request body.

## Known limitations, honestly

- Real email/password auth exists (`POST /auth/signup` / `POST /auth/login`),
  with a real password-reset flow (`POST /auth/forgot-password` /
  `POST /auth/reset-password`, rate-limited, revokes prior API keys on
  completion) and real role-based access (`user`/`admin`, admin-only
  endpoints under `/admin`, a last-admin safety check so you can't
  accidentally lock every admin endpoint out). Password reset emails
  currently only reach one verified address — AWS SES is still in
  sandbox mode, requiring a real domain + DKIM/SPF/DMARC records and a
  production-access request before real other users can receive one.
- **Frontend/MCP tests exist but have never actually been run** — no
  registry access in the environment that wrote them; run `npm test`
  and `pytest` (`mcp_server/`) locally for the real first verification
- Momentum/factor trading-day alignment across tickers is positional,
  not by explicit calendar date — a documented simplification, fine
  for ordinary listed equities, a known edge case for a very recent
  IPO or a halted stock
- App Runner is closed to new customers as of April 2026 — fine for
  this existing instance, worth knowing before starting a new project
  on it
