# demo-gnews-remotemcp-auth

A **remote, authenticated** [MCP](https://modelcontextprotocol.io/) (Model
Context Protocol) server that brings the [GNews API](https://gnews.io/) to any AI
agent — protected with **OAuth 2.1** and **deployed to the public internet**.

It's built with the **FastMCP** tools from the official
[Python SDK](https://github.com/modelcontextprotocol/python-sdk), wrapped in a
[FastAPI](https://fastapi.tiangolo.com/) app that adds an OAuth auth middleware
([Scalekit](https://www.scalekit.com/) as the authorization server) and the
discovery endpoint required by the MCP authorization spec. The result is a news
search service that an agent connects to **by URL** and can only use after a real
OAuth login.

> **Live deployment:** `https://mcp-dev-guide.onrender.com/mcp/`
> Hosted on [Render](https://render.com/), connected to **Claude** — the OAuth
> flow runs in the browser and the GNews tools work end-to-end.

## What this demo shows

This is the "final boss" of a remote MCP setup — everything wired together and
actually running in production:

- A FastMCP server exposing real tools (`search_news`, `get_top_headlines`).
- **Streamable HTTP** transport, so the server is a long-lived web service rather
  than a local subprocess.
- **OAuth 2.1** enforcement on every tool call, with scope checks (`gnews:read`).
- The OAuth **discovery endpoint** that lets clients (Claude, VS Code, …) find
  the authorization server and authenticate automatically.
- A working **public deployment** that a hosted client like Claude can reach.

## What's inside

| Tool                | GNews endpoint                          | Purpose                              |
| ------------------- | --------------------------------------- | ------------------------------------ |
| `search_news`       | `https://gnews.io/api/v4/search`        | Search articles by keyword/filters.  |
| `get_top_headlines` | `https://gnews.io/api/v4/top-headlines` | Trending headlines by category.      |

Each tool's parameters (language, country, date range, sorting, pagination…) are
generated from the typed Python signatures in [`gnews.py`](gnews.py), so the
agent knows exactly what to pass.

## Architecture

```
                ┌───────────────────────── FastAPI (main.py) ─────────────────────────┐
  MCP client ──▶│  GET /.well-known/oauth-protected-resource/mcp  → resource metadata   │
  (HTTP +       │  AuthMiddleware (auth.py)                                             │
   Bearer       │     ├─ /.well-known/*  → pass through (no auth)                       │
   token)       │     └─ everything else → require + validate Bearer token via Scalekit │
                │  mount "/"  → gnews_mcp.streamable_http_app()   (MCP endpoint /mcp)    │
                └──────────────────────────────────────────────────────────────────────┘
                                   │ validate_token (issuer, audience, scope gnews:read)
                                   ▼
                          Scalekit authorization server
                                   │
                                   ▼
                            GNews API (the data)
```

The OAuth handshake the server drives:

1. Client calls `POST /mcp` **without** a token → `401` + a `WWW-Authenticate`
   header pointing at the resource-metadata URL.
2. Client fetches `/.well-known/oauth-protected-resource/mcp` → learns which
   **authorization server** (Scalekit) to use.
3. Client registers / reuses an OAuth client and runs the OAuth 2.1 + PKCE login
   in the browser.
4. Client retries `POST /mcp` with `Authorization: Bearer <token>`. The
   middleware checks the token's **issuer**, **audience**, and — for
   `tools/call` — the `gnews:read` **scope**, then forwards the request to the
   GNews tool.

## Setup (local)

Uses [uv](https://docs.astral.sh/uv/) and Python 3.13.

```bash
uv sync
cp .env.example .env
```

Fill in `.env`:

| Variable | Meaning |
| --- | --- |
| `GNEWS_API_KEY` | Your key from [gnews.io](https://gnews.io/) (the news data source). |
| `SCALEKIT_ENVIRONMENT_URL` | Scalekit environment URL (token **issuer**). |
| `SCALEKIT_CLIENT_ID` / `SCALEKIT_CLIENT_SECRET` | Scalekit client credentials. |
| `SCALEKIT_RESOURCE_METADATA_URL` | URL of this server's discovery endpoint. |
| `SCALEKIT_AUDIENCE_NAME` | Resource **audience** tokens are validated against (your MCP server URL). |
| `METADATA_JSON_RESPONSE` | Single-line JSON returned by the discovery endpoint (RFC 9728). |
| `PORT` | Port to listen on (default `10000`). |

> In `METADATA_JSON_RESPONSE`, the `resource` field must match the URL clients
> connect to (e.g. `https://mcp-dev-guide.onrender.com/mcp`). If it differs, the
> client rejects the metadata and the OAuth flow silently fails.

## Running (local)

```bash
uv run main.py
```

Serves on `http://0.0.0.0:10000` — MCP endpoint at `/mcp`, discovery at
`/.well-known/oauth-protected-resource/mcp`. Keep the process alive; it's a
remote server clients connect to by URL.

Sanity checks:

```bash
curl -s http://localhost:10000/.well-known/oauth-protected-resource/mcp   # → 200 + metadata JSON
curl -i -X POST http://localhost:10000/mcp -H 'Content-Type: application/json' -d '{}'  # → 401 + WWW-Authenticate
```

## Deployment (Render)

This server runs live on [Render](https://render.com/). Because it's part of a
monorepo, the service points at this subdirectory:

- **Root directory:** `05_demo-gnews-remotemcp-auth`
- **Build command:** `uv sync`
- **Start command:** `uv run main.py` (Uvicorn binds `0.0.0.0:$PORT`)
- **Environment variables:** `GNEWS_API_KEY` + all `SCALEKIT_*` + `METADATA_JSON_RESPONSE`
  set in the Render dashboard (never committed — `.env` is gitignored).

Once deployed, the public MCP endpoint is:

```
https://mcp-dev-guide.onrender.com/mcp/
```

Make sure `SCALEKIT_AUDIENCE_NAME`, the `resource` in `METADATA_JSON_RESPONSE`,
and the Scalekit-registered resource identifier all match this public URL.

## Connecting it to an agent

### Claude (tested ✅)

Add the remote server by its public URL. Claude discovers the metadata, opens a
browser for the Scalekit login, stores the token, and then exposes `search_news`
and `get_top_headlines` as tools:

```
https://mcp-dev-guide.onrender.com/mcp/
```

### VS Code

```json
{
  "servers": {
    "gnews": {
      "type": "http",
      "url": "https://mcp-dev-guide.onrender.com/mcp/"
    }
  }
}
```

### Claude Code (CLI)

```bash
claude mcp add --transport http gnews https://mcp-dev-guide.onrender.com/mcp/
claude mcp list      # gnews ✓ connected after you authenticate
```

## Tools reference

### `search_news`
Search worldwide articles by keyword.
- **`q`** (required) — keywords; supports `"phrases"`, `AND`, `OR`, `NOT`.
- `lang`, `country` — 2-letter language / country codes.
- `max_articles` — 1–100 (default 10).
- `search_in` — fields to search: `title`, `description`, `content`.
- `nullable` — fields allowed to be null: `description`, `content`, `image`.
- `date_from`, `date_to` — ISO 8601 bounds.
- `sortby` — `publishedAt` (default) or `relevance`.
- `page` — pagination.

### `get_top_headlines`
Trending headlines by category.
- `category` — `general` (default), `world`, `nation`, `business`, `technology`,
  `entertainment`, `sports`, `science`, `health`.
- `lang`, `country`, `max_articles`, `nullable`, `date_from`, `date_to`, `q`,
  `page` — same meaning as in `search_news`.

Both require a token carrying the `gnews:read` scope and return GNews' standard
`{ totalArticles, articles[] }` payload.

## Troubleshooting

- **`TypeError: fetch failed`** — server not reachable (local process stopped, or
  Render service asleep/cold-starting). Free Render instances spin down when
  idle; the first request after a pause can be slow.
- **`Could not fetch resource metadata` / client uses the wrong auth server** —
  discovery returned non-200 or `resource` doesn't match the client URL. Check
  `METADATA_JSON_RESPONSE`.
- **`Token validation failed`** — issuer/audience/scope mismatch; align
  `SCALEKIT_ENVIRONMENT_URL` (issuer), `SCALEKIT_AUDIENCE_NAME` (audience), and
  the `gnews:read` scope with what Scalekit issues.

## Project structure

```
main.py        # FastAPI app: lifespan, CORS, discovery endpoint, auth, MCP mount
auth.py        # AuthMiddleware: Bearer extraction + Scalekit token validation
config.py      # Settings loaded from .env
gnews.py       # FastMCP server with search_news / get_top_headlines
examples.py    # Example usage
test_server.py # Tests
Makefile       # install / run / test / format helpers
```
</content>
