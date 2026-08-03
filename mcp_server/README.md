# FinInsight MCP Server

Lets Claude Desktop (or any MCP client) read and manage your FinInsight
watchlist, portfolios, and research directly in conversation — no
`curl`, no dashboard.

**Honest caveat**: the tool logic itself was written and syntax-checked
against the deployed API, but the MCP server process wasn't actually
run against a real client until it was tested live — which caught a
real bug (a bare `python3` in the config resolves to a different
interpreter than the one you install dependencies into, since Claude
Desktop launches this as a subprocess with its own minimal
environment). Fixed below by using the venv's absolute path. If
something else in the setup doesn't work exactly as described, run the
server directly first (see Troubleshooting) to see the real error
before assuming the config is wrong.

## 1. Install dependencies

Use an isolated virtualenv, not your system Python or the main app's
venv — this project's dependencies conflict with the main app's pinned
FastAPI/Starlette versions if installed into the same one, and more
importantly, **Claude Desktop launches this as a subprocess with its
own minimal environment, which usually does NOT include your shell's
activated venv** — a bare `python3` in the config below can silently
resolve to a completely different interpreter than the one you tested
with. Point the config at this venv's Python by its full absolute
path, not a bare command name.

```bash
cd mcp_server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Get an API key

If you don't already have a FinInsight account:
```bash
curl -X POST "https://p8xpcshdn9.us-east-1.awsapprunner.com/auth/signup" \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "yourpassword"}'
```

Already have one and just want a second key for MCP specifically?
Log in instead — same shape, mints a fresh key each time:
```bash
curl -X POST "https://p8xpcshdn9.us-east-1.awsapprunner.com/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "yourpassword"}'
```

Copy the `plaintext_key` from the response — shown exactly once, same
as every other API key in this platform.

## 3. Configure Claude Desktop

Find Claude Desktop's config file:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

Add (or merge into) an `mcpServers` entry — note `command` is the FULL
ABSOLUTE PATH to the venv's Python (from step 1), not a bare `python3`:

```json
{
  "mcpServers": {
    "fininsight": {
      "command": "/absolute/path/to/fininsight/mcp_server/.venv/bin/python3",
      "args": ["/absolute/path/to/fininsight/mcp_server/server.py"],
      "env": {
        "FININSIGHT_API_KEY": "fi_live_your_actual_key_here"
      }
    }
  }
}
```

Replace `/absolute/path/to/fininsight/` with the real path on your
machine (relative paths don't work here — Claude Desktop launches this
as a subprocess from its own working directory, not yours).

If you're running against a local dev server instead of production,
also add:
```json
"FININSIGHT_API_URL": "http://localhost:8000"
```

## 4. Restart Claude Desktop completely

Not just close the window — fully quit and reopen, same as every other
config-file change we've hit this session. MCP servers are loaded at
startup.

## 5. Verify it connected

In Claude Desktop, look for a small tools/plug icon near the message
input — clicking it should show `fininsight` with 47 tools listed. If
it's not there, check Claude Desktop's logs (usually accessible from
its settings/developer menu) for a startup error from this server.

## Try it

Ask Claude something like:
- "What's on my FinInsight watchlist?"
- "Create a portfolio called Growth and add 10 shares of AAPL at $150"
- "What's the risk profile of my Retirement portfolio?"
- "Give me my daily brief" (note: this one costs real money — it's an LLM call)
- "Create a theme called AI Infrastructure, tag NVDA and AVGO into it, then synthesize it" (also a real LLM call)
- "What's NVDA's factor score?" or "Rank the S&P 500 by factor score"
- "Ingest the SPY ETF" then "What's SPY's factor score?" (expect Value/Quality/Growth to come back null — honest, not a bug, funds have no income statement)
- "Split $10,000 across NVDA, AMD, and AVGO using risk parity"

## Tests

```bash
cd mcp_server
FININSIGHT_API_KEY=test_key python3 tests/run_tests.py
```

9 tests against the REAL, unmodified `server.py` — including a
systematic sweep checking every one of the 47 tools against the exact
REST path it should hit, which self-checks that no new tool gets added
without a corresponding entry (see `tests/test_server.py`). Since
neither `httpx` nor `mcp` needs to be actually installed to run these
(they're faked at the `sys.modules` level — see `tests/fake_deps.py`),
this also works as a zero-dependency sanity check before you even set
up the real venv. Also runnable with plain `pytest tests/` if you have
pytest installed — every test is a normal sync function internally
managing its own `asyncio.run()`, no special plugin needed.

## Troubleshooting

**"FININSIGHT_API_KEY environment variable is required"** — the `env`
block in the config didn't get picked up. Double-check the JSON is
valid (a trailing comma or missing brace will silently break the whole
file) and that you fully restarted Claude Desktop.

**Tools appear but every call returns a 401** — the API key is wrong,
expired, or has a typo. Test it directly first:
```bash
curl "https://p8xpcshdn9.us-east-1.awsapprunner.com/watchlist" -H "X-Api-Key: YOUR_KEY"
```
If that fails too, the key itself is the problem, not the MCP layer.

**Claude Desktop doesn't show the tools icon at all** — the server
process likely crashed on startup. Try running it directly to see the
real error, same principle as running Postgres in the foreground
earlier this session:
```bash
FININSIGHT_API_KEY=your_key python3 server.py
```
This should print MCP server startup messages and hang waiting for
stdio input (that's correct — Ctrl+C to stop). If it errors instead,
paste that error.
