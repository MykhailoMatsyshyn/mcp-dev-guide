# remote-mcp-fastapi

A **remote** [MCP](https://modelcontextprotocol.io/) (Model Context Protocol)
server that runs over HTTP instead of stdio. It is built with the high-level
**FastMCP** interface from the official
[Python SDK](https://github.com/modelcontextprotocol/python-sdk) and served by
[**FastAPI**](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/),
using MCP's **Streamable HTTP** transport.

Unlike a stdio server (which a client launches as a local subprocess), this one
is a long-running web service. A single FastAPI app hosts **two independent MCP
servers** side by side, each mounted under its own URL path, so one process can
expose several tool sets to any number of remote agents.

## What's inside

Two FastMCP servers are mounted onto one FastAPI application:

| Mount path | Module                         | Tools                             |
| ---------- | ------------------------------ | --------------------------------- |
| `/docs`    | [`docs_mcp.py`](docs_mcp.py)   | `get_documentation_from_database` |
| `/email`   | [`email_mcp.py`](email_mcp.py) | `get_emails`, `write_email`       |

Each FastMCP instance exposes a Streamable HTTP app, and
[`main.py`](main.py) `mount`s them under `/docs` and `/email`. The MCP endpoint
itself lives at the `/mcp` sub-path of each mount, so the two servers are reached
at:

- `http://localhost:10000/docs/mcp`
- `http://localhost:10000/email/mcp`

The tools here return **mocked** data — they stand in for a real database or mail
backend (see the `## actual implementation would query a real database here`
comments). The point of the project is the *remote transport wiring*, not the
business logic. As with any FastMCP server, each tool's schema is generated
automatically from the typed Python signature, so the agent knows exactly what
arguments to pass.

## How it works

```
              ┌──────────────────────── FastAPI (main.py) ───────────────────────┐
              │                                                                   │
 MCP client ─▶│  CORS middleware                                                  │
 (HTTP)       │    ├── mount "/docs"   →  docs_mcp.streamable_http_app()          │
              │    └── mount "/email"  →  email_mcp.streamable_http_app()         │
              │                                                                   │
              │  lifespan: runs each server's session_manager for the app's life │
              └───────────────────────────────────────────────────────────────────┘
```

Two details make the multi-server setup work:

- **Lifespan management** — Streamable HTTP servers keep a `session_manager`
  that must be running while the app serves requests. The `lifespan` context
  manager in `main.py` enters both managers via an `AsyncExitStack`, so they
  start on boot and shut down cleanly together.
- **CORS** — `allow_origins=["*"]` is enabled so browser-based MCP clients (and
  the MCP Inspector) can call the endpoints. Tighten this before any real
  deployment.

## Setup

This project uses [uv](https://docs.astral.sh/uv/). Install dependencies into a
local virtual environment:

```bash
uv sync
```

`uv` reads [`pyproject.toml`](pyproject.toml) / `uv.lock` and installs FastAPI,
Uvicorn, and the MCP SDK. Python **3.11+** is required (see `.python-version`).

## Running

```bash
uv run main.py
```

The server starts on **http://localhost:10000** with debug logging. You should
see both session managers start:

```
StreamableHTTP session manager started
StreamableHTTP session manager started
INFO:     Uvicorn running on http://localhost:10000 (Press CTRL+C to quit)
```

> A plain `GET http://localhost:10000/docs/` returns **404** — that's expected.
> This is not Swagger UI and not a REST API; the MCP endpoint expects MCP-protocol
> requests (`POST`) at `/docs/mcp` and `/email/mcp`. Use an MCP client or the
> Inspector to talk to it, not a browser address bar.

For local development you can enable auto-reload by running through Uvicorn
directly:

```bash
uv run uvicorn main:app --host localhost --port 10000 --reload
```

## Testing & debugging

I tested the server with the official
[**MCP Inspector**](https://github.com/modelcontextprotocol/inspector). For a
remote (HTTP) server you don't launch it as a subprocess — instead start the
Inspector and connect to a running endpoint:

```bash
# in one terminal
uv run main.py

# in another
npx @modelcontextprotocol/inspector
```

In the Inspector UI, choose the **Streamable HTTP** transport and point it at one
of the endpoints, e.g. `http://localhost:10000/docs/mcp` or
`http://localhost:10000/email/mcp`. It lists the discovered tools with their
auto-generated schemas and lets you fire test calls and inspect raw responses —
handy for verifying each mount before connecting a real agent.

## Connecting the server to an agent

Because this is a remote server, clients connect by **URL**, not by spawning a
process. Each mount is registered separately.

### Claude Code (CLI)

Use `claude mcp add` with the HTTP transport:

```bash
claude mcp add --transport http docs  http://localhost:10000/docs/mcp
claude mcp add --transport http email http://localhost:10000/email/mcp
```

Verify it:

```bash
claude mcp list          # should show both servers as ✓ connected
```

Inside a session, run `/mcp` to see the servers and their tools. Add `-s user`
to make a server available in every project instead of just the current one.

### VS Code (built-in agent)

Add an `.vscode/mcp.json` file so the editor's agent can discover the servers
over HTTP:

```json
{
  "servers": {
    "docs": {
      "type": "http",
      "url": "http://localhost:10000/docs/mcp"
    },
    "email": {
      "type": "http",
      "url": "http://localhost:10000/email/mcp"
    }
  }
}
```

### Claude Desktop / other clients

Any MCP client that supports remote servers works — point it at the URLs above.
For clients that only speak stdio, bridge them with
[`mcp-remote`](https://www.npmjs.com/package/mcp-remote):

```json
{
  "mcpServers": {
    "docs": {
      "command": "npx",
      "args": ["mcp-remote", "http://localhost:10000/docs/mcp"]
    }
  }
}
```

## Tools reference

### `/docs` server

#### `get_documentation_from_database`

Returns documentation for the project from the (mocked) database. Takes no
arguments. Useful for an agent to figure out what the project is about. Returns a
dict with `title`, `body`, and `source`.

### `/email` server

#### `get_emails`

Returns emails from the (mocked) database. Takes no arguments. Returns a dict
with `title`, `body`, and `source`.

#### `write_email`

Composes/sends an email (mocked — currently just echoes the input).

- **`recipient`** (required) — the email address to send to.
- **`subject`** (required) — the email subject.
- **`body`** (required) — the email body.

Returns a dict with `status` and a confirmation `message`.

## Notes & next steps

- Both FastMCP instances are currently constructed as
  `FastMCP("mcp-documentation-server")`; rename the one in `email_mcp.py` (e.g.
  `"mcp-email-server"`) so the two servers are easier to tell apart in clients.
- The tool bodies return mocked data — swap in a real database / mail provider
  where the placeholder comments are.
- Before deploying remotely, restrict CORS `allow_origins`, bind to `0.0.0.0`
  behind a reverse proxy, and add authentication.
</content>
