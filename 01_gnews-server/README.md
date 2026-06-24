# gnews-server

An [MCP](https://modelcontextprotocol.io/) (Model Context Protocol) server that
brings the [GNews API](https://gnews.io/) to any AI agent. It is built with the
high-level **FastMCP** interface from the official
[Python SDK](https://github.com/modelcontextprotocol/python-sdk) and exposes the
GNews search and headlines endpoints as agent tools.

Once connected to an MCP client (Claude Code, Claude Desktop, VS Code, Cursor, …),
the agent can fetch real, up-to-date news on demand — e.g. *"find the latest
articles about AI regulation"* or *"give me today's top technology headlines"*.

## What's inside

Two tools are exposed, one per GNews endpoint:

| Tool            | GNews endpoint                          | Purpose                             |
| --------------- | --------------------------------------- | ----------------------------------- |
| `search_news`   | `https://gnews.io/api/v4/search`        | Search news articles by keyword.    |
| `top_headlines` | `https://gnews.io/api/v4/top-headlines` | Fetch top breaking-news headlines.  |

The agent doesn't need to know anything about GNews in advance: each tool's
parameters, constraints, and descriptions are generated automatically from the
typed Python function signatures, so the model knows exactly what arguments to
pass and when to call each tool.

## How it was built

This server was written with **Claude** using the following prompt:

> Consider this documentation on how to create MCP servers:
> - MCP: https://modelcontextprotocol.info/llms-full.txt
> - Python SDK: https://github.com/modelcontextprotocol/python-sdk
>
> Create an MCP server that integrates the GNews API using the high-level
> interface FastMCP. The API has different endpoints, here are their
> documentation pages:
> - Search endpoint: https://docs.gnews.io/endpoints/search-endpoint
> - Top Headlines endpoint: https://docs.gnews.io/endpoints/top-headlines-endpoint

Claude read the protocol docs and the GNews endpoint references, then generated
the FastMCP server in [`src/gnews_server/server.py`](src/gnews_server/server.py),
mapping every documented query parameter to a typed, validated tool argument.

## Setup

1. Get a free API key from [gnews.io](https://gnews.io/).
2. Install dependencies (this project uses [uv](https://docs.astral.sh/uv/)):

   ```bash
   uv sync
   ```

3. Provide the key via the `GNEWS_API_KEY` environment variable.

## Running

```bash
GNEWS_API_KEY=your_key_here uv run gnews-server
```

The server speaks MCP over **stdio** — an MCP client launches it as a
subprocess and talks to it over standard input/output.

## Testing & debugging

I tested the server during development with the official
[**MCP Inspector**](https://github.com/modelcontextprotocol/inspector), a UI for
inspecting and calling MCP tools without wiring up a full client:

```bash
GNEWS_API_KEY=your_key_here \
  npx @modelcontextprotocol/inspector uv run gnews-server
```

The Inspector opens in the browser, lists the discovered tools (`search_news`,
`top_headlines`) with their auto-generated schemas, and lets you fire test calls
and inspect the raw responses — handy for verifying the GNews requests before
connecting any agent.

## Connecting the server to an agent

I connected this server to two different agents.

### Claude Code (CLI)

Register the server with the `claude mcp add` command. `--directory` points uv at
this project so it works from anywhere:

```bash
claude mcp add gnews \
  --env GNEWS_API_KEY=your_key_here \
  -- uv --directory /absolute/path/to/gnews-server run gnews-server
```

Verify it:

```bash
claude mcp list          # should show "gnews ✓ connected"
```

Inside a Claude Code session, run `/mcp` to see the server and its tools. Add
`-s user` to the command above to make the server available in every project
instead of just the current one.

### VS Code (built-in agent)

Add an `.vscode/mcp.json` file (or use the global MCP config) so the editor's
agent can discover the server:

```json
{
  "servers": {
    "gnews": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/gnews-server", "run", "gnews-server"],
      "env": {
        "GNEWS_API_KEY": "your_key_here"
      }
    }
  }
}
```

The agent then lists `search_news` and `top_headlines` among its available tools
and calls them whenever a request needs live news.

### Claude Desktop / other clients

Any MCP client works — add this to its config (e.g. Claude Desktop's
`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "gnews": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/gnews-server", "run", "gnews-server"],
      "env": {
        "GNEWS_API_KEY": "your_key_here"
      }
    }
  }
}
```

## Tools reference

### `search_news`

Search worldwide articles matching keywords.

- **`q`** (required) — search keywords (max 200 chars; supports `"phrases"`, `AND`, `OR`, `NOT`).
- `lang`, `country` — 2-letter language / publication-country codes.
- `max` — number of articles, 1–100 (default 10).
- `in_` — maps to the GNews `in` param; attributes to search: `title`, `description`, `content` (comma-separated).
- `nullable` — attributes allowed to be null: `description`, `content`, `image`.
- `from_`, `to` — `from_` maps to the GNews `from` param; ISO 8601 publication-date bounds.
- `sortby` — `publishedAt` (default) or `relevance`.
- `page` — pagination (max 1000 articles total).
- `truncate` — if `true`, truncate the `content` field.

### `top_headlines`

Fetch top headlines by category.

- `category` — one of `general` (default), `world`, `nation`, `business`,
  `technology`, `entertainment`, `sports`, `science`, `health`.
- `lang`, `country`, `max`, `q`, `nullable`, `from_`, `to`, `page`, `truncate` —
  same meaning as in `search_news`.

Both tools return a dict with `totalArticles` and an `articles` list. Each
article contains `id`, `title`, `description`, `content`, `url`, `image`,
`publishedAt`, `lang`, and a `source` object (`id`, `name`, `url`, `country`).
</content>
</invoke>
