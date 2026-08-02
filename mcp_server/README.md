# FinInsight MCP Server

Lets Claude Desktop (or any MCP client) read and manage your FinInsight
watchlist, portfolios, and research directly in conversation — no
`curl`, no dashboard.

**Honest caveat**: this was written and syntax-checked, but never run
against a real MCP client during development (no network access in the
build environment). If something in the setup below doesn't work
exactly as described, that's the most likely place — walk through it
step by step and report back what actually happens at each stage,
same as we debugged the AWS deployment.

## 1. Install dependencies

```bash
cd mcp_server
pip install -r requirements.txt
```

## 2. Get an API key

```bash
curl -X POST "https://p8xpcshdn9.us-east-1.awsapprunner.com/api-keys?user_id=YOUR_NAME&name=mcp-client"
```

Copy the `plaintext_key` from the response — shown exactly once, same
as every other API key in this platform.

## 3. Configure Claude Desktop

Find Claude Desktop's config file:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

Add (or merge into) an `mcpServers` entry:

```json
{
  "mcpServers": {
    "fininsight": {
      "command": "python3",
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
input — clicking it should show `fininsight` with 35 tools listed. If
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
