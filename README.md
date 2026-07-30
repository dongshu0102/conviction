# FinInsight — AI Financial Intelligence Platform

An AI-native financial platform for individual investors: real S&P 500
data, deterministic financial computation where correctness matters, and
an LLM layer for synthesis, conversation, and action — grounded in that
data, never guessing at numbers it should have looked up.

Live at **https://p8xpcshdn9.us-east-1.awsapprunner.com** (API) — see
`frontend/` for the web app and `mcp_server/` for the Claude
Desktop/claude.ai integration.

## What's built

**Data foundation** — 503 S&P 500 companies ingested from Financial
Modeling Prep (profile + 5 years of annual statements), stored with a
typed-fields-plus-raw-JSON schema so no vendor data is ever silently
dropped.

**Three deterministic agents** — Financial Analysis (margins, growth,
ROE/ROA, leverage), Valuation (P/E, P/S, EV/EBITDA against live
quotes), and Company Research (LLM-grounded, but only ever generated
from real ingested statements — raises before calling the model if no
data exists, rather than letting it improvise).

**Portfolio & watchlist** — full CRUD, live valuation, and Herfindahl-
index-based concentration/sector/leverage risk analysis.

**Continuous monitoring** — price-move alerts via a standalone
cron-invoked script (`scripts/run_monitoring.py`), deliberately not an
in-process scheduler (that pattern caused a real multi-worker race
condition earlier in development — see `Dockerfile` comments).

**Daily Brief** — an AI narrative synthesizing watchlist moves,
portfolio performance, and alerts into one short paragraph, grounded
in the same structured data a person could otherwise read directly.

**Real API key authentication** — SHA-256 hashed, shown once, with
ownership checks on every portfolio-scoped endpoint (a gap that was
genuinely absent in earlier iterations and got fixed alongside the
auth rollout, not before).

**Chat agent** — 11 tools (watchlist, portfolios, valuation, risk,
analysis, research, rebalancing suggestions, a value/quality stock
screener) via Anthropic's tool-use API, streamed to the frontend
through the Vercel AI SDK. Deterministic computation stays
deterministic even inside the chat — e.g. rebalancing share counts are
computed by a plain use case, never estimated by the model.

**MCP server** — the same capabilities, exposed to Claude Desktop /
claude.ai as 18 tools, for anyone who wants programmatic/conversational
access outside the web app.

**Web frontend** — Next.js, real streaming chat, a dark "Refined
Terminal" design, deployed as its own App Runner service alongside the
API (no VPC connector needed — it only calls the public API over
HTTPS).

## Architecture

**Clean Architecture, four layers, strict dependency direction (inward only):**

```
src/
├── domain/           # Entities + repository interfaces. Zero external deps.
├── application/       # Use cases + provider/agent interfaces. Framework-free.
│   ├── use_cases/      # One class per business operation
│   └── interfaces/     # FinancialDataProvider, ResearchGenerator, ChatAgent, ...
├── infrastructure/    # Concrete implementations of the above interfaces.
│   ├── data_providers/ # FinancialModelingPrepProvider (FMP adapter)
│   ├── llm_providers/  # Anthropic adapters — research, brief, chat
│   └── persistence/    # SQLAlchemy models + repository implementations
└── api/                # FastAPI — routers, Pydantic schemas, DI wiring

frontend/               # Next.js web app (separate deployable, own Dockerfile)
mcp_server/              # MCP server for Claude Desktop (separate deployable)
scripts/                 # Bulk ingestion, monitoring cron job
```

**Dependency rule**: `domain` knows nothing about the other three layers.
`application` knows about `domain` only. `infrastructure` and `api` depend
inward. This is what let the LLM provider swap from a single-purpose
research generator to a full tool-calling chat agent without touching
domain logic — the interface (`ChatAgent`) is the seam; Anthropic's
specific wire format lives only in `infrastructure/llm_providers/`.

## Local setup

### Backend

```bash
cp .env.example .env   # set FMP_API_KEY, ANTHROPIC_API_KEY, DATABASE_URL
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
reads it at startup, not on hot-reload. This has been the single most
common local-testing snag in this project's history.

### MCP server (Claude Desktop / claude.ai)

See `mcp_server/README.md` for the full setup — it needs its own
isolated virtualenv (its dependencies conflict with the main app's
pinned FastAPI/Starlette versions if installed into the same one).

## Try it

```bash
# Ingest a company
curl -X POST "http://localhost:8000/companies/AAPL/ingest?years=5"

# Create an API key (the closest thing to "signup" this MVP has)
curl -X POST "http://localhost:8000/api-keys?user_id=YOUR_NAME&name=cli"

# Everything else needs that key
curl "http://localhost:8000/companies/AAPL/analysis" -H "X-Api-Key: fi_live_..."
curl -X POST "http://localhost:8000/watchlist/AAPL" -H "X-Api-Key: fi_live_..."
curl -X POST "http://localhost:8000/chat" -H "X-Api-Key: fi_live_..." \
  -H "Content-Type: application/json" \
  -d '{"message": "what is on my watchlist", "history": []}'
```

## Tests

```bash
pytest tests/ -v
```

59 tests, all against in-memory fakes (`tests/unit/fakes.py`) — no
database, no network, no mocking framework. If a repository or agent
interface changes shape, the fakes fail to implement it and the suite
fails to even collect, catching the break at the earliest possible
point. Frontend/MCP server code has no automated test suite yet — real
usage this session (streaming chat, screener output, redesign) was the
verification, same limitation as any code that needed a live network
connection this sandbox didn't have.

## Database migrations

```bash
alembic upgrade head         # apply all pending migrations
alembic revision -m "add X"  # create a new empty migration to edit by hand
alembic downgrade -1         # roll back one migration
```

## Deployment (production)

AWS: RDS Postgres (private), ECR, App Runner (backend + separate
frontend service), Secrets Manager, GitHub Actions OIDC (no long-lived
AWS credentials in CI). The backend's VPC connector lives on a
dedicated private subnet routed through a NAT Gateway to a *separate*
public subnet — an earlier attempt that put the NAT Gateway in the
same subnet it was supposed to route for caused a real routing loop
that took a full debugging session to trace via CloudTrail. The
frontend needs no VPC connector at all — it only calls the public API
over HTTPS.

## Known limitations, honestly

- No real user accounts/sessions — API keys are the whole auth story
- Monitoring/alerts only track tickers actively on someone's watchlist,
  not the full ingested universe
- The stock screener works on a caller-named, bounded list of tickers
  (~15 max) — a true "screen the whole S&P 500" feature needs a
  periodic batch-valuation job that doesn't exist yet
- No "hot stocks" / price-momentum list — would need historical price
  storage this system doesn't have (only one live snapshot per ticker,
  for monitoring diffs)
- Frontend has no automated tests
