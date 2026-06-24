# simple-mcp-rag

A **Retrieval-Augmented Generation (RAG)** server exposed over [MCP](https://modelcontextprotocol.io/)
(Model Context Protocol). It turns a folder of documents (PDF, DOCX, PPTX…) into
a searchable knowledge base and hands an AI agent the tools to query it — built
with [FastMCP](https://github.com/jlowin/fastmcp), [ChromaDB](https://docs.trychroma.com/)
for the vector store, and [LlamaParse](https://docs.cloud.llamaindex.ai/) for
document parsing.

## Why put RAG behind MCP?

Normally, RAG lives *inside* one application: you wire an embedding model, a
vector DB, and a retrieval step into a single chatbot, and only that chatbot can
use it. The knowledge is locked to the app.

Wrapping RAG as an **MCP server** flips that around. Retrieval becomes a
**reusable tool** that *any* MCP-capable agent can call — Claude Desktop, VS
Code, Cursor, a HuggingFace chat, your own agent — without re-implementing
chunking, embeddings, or storage. The model decides *when* it needs your
documents and calls `query_documents` on its own, the same way it would call any
other tool.

So the value is:

- **One knowledge base, many clients.** Build the index once; plug it into any
  agent over a standard protocol.
- **Separation of concerns.** The agent does reasoning; the server owns parsing,
  embedding, storage, and retrieval.
- **The model drives retrieval.** Instead of always stuffing context in, the
  agent fetches only what it needs, when it needs it.

That's the whole point of this project: a minimal, readable example of *RAG as an
MCP tool*.

## Architecture

```
  ┌──────────────┐   ingest_data_directory   ┌────────────────────────────────┐
  │  ./data/*    │ ────────────────────────▶ │  LlamaParse  →  chunk (8k chars) │
  │ pdf/docx/ppt │                            │        ↓                         │
  └──────────────┘                            │   ChromaDB (embed + persist)     │
                                              │        ./chroma/                 │
                                              └────────────────────────────────┘
                                                          ▲
                                                          │ query_documents (semantic search)
                                                          │
   MCP client  ───────────  Streamable HTTP  ───────────  FastMCP "RAG Server"
   (agent)                  http://127.0.0.1:8000/mcp
```

Two phases:

1. **Ingestion** — `ingest_data_directory` reads every file in `./data`, sends it
   through LlamaParse to extract clean text, splits it into ~8 000-char chunks,
   and stores them in a local ChromaDB collection (`rag_documents`). ChromaDB
   computes the embeddings locally and persists everything to `./chroma`.
2. **Retrieval** — when the agent calls `query_documents`, ChromaDB embeds the
   query, runs a similarity search, and the server returns the top chunks with
   their source file and similarity score.

## What's inside

The server (`rag_server.py`) exposes four MCP tools:

| Tool                    | Purpose                                                          |
| ----------------------- | ---------------------------------------------------------------- |
| `ingest_data_directory` | Parse everything in `./data` and (re)build the vector DB.        |
| `query_documents`       | Semantic search over the indexed chunks (`query`, `n_results`).  |
| `list_ingested_files`   | List which files are currently in the database, and chunk count. |
| `server_status`         | Report data dir, DB dir, ingested file count, and key status.    |

## Setup

This project uses [uv](https://docs.astral.sh/uv/) and Python 3.13.

```bash
uv sync
cp .env.example .env
```

Fill in `.env`:

| Variable              | Meaning                                                            |
| --------------------- | ----------------------------------------------------------------- |
| `LLAMA_CLOUD_API_KEY` | LlamaParse API key (from [LlamaCloud](https://cloud.llamaindex.ai/)) — needed to parse PDF/DOCX/PPTX. |
| `LLAMA_RAG_DATA_DIR`  | Source documents folder (optional; defaults to `./data`).         |
| `LLAMA_RAG_DB_DIR`    | ChromaDB persistence folder (optional; defaults to `./chroma`).    |

Then drop some documents into `./data` and you're ready.

## Running

```bash
uv run rag_server.py
```

The server boots, initializes ChromaDB, and serves MCP over **Streamable HTTP**
at `http://127.0.0.1:8000/mcp`. Keep the process running — it's a long-lived
service that clients connect to by URL.

> First run downloads the embedding model, so it can take a moment. Run
> `ingest_data_directory` once (from any connected client or the Inspector) to
> build the index before querying.

## Testing & debugging

I built this up incrementally and **debugged locally first**, before exposing it
to any cloud client:

1. **MCP Inspector** — the fastest loop. Start the Inspector, connect to
   `http://127.0.0.1:8000/mcp` over Streamable HTTP, and call the tools by hand:
   `ingest_data_directory` to index, `list_ingested_files` to confirm, then
   `query_documents` to check the retrieved chunks and similarity scores.

   ```bash
   npx @modelcontextprotocol/inspector
   ```

2. **Server logs** — `rag_server.py` logs each step (DB dir, documents loaded,
   chunks ingested, query results), which made it easy to see whether parsing or
   retrieval was the problem.

Only once it worked end-to-end locally did I expose it to a real agent.

## Exposing it publicly with ngrok

The server runs on `localhost`, but a cloud-hosted MCP client (like a
**HuggingFace chat**) can't reach your machine directly. [ngrok](https://ngrok.com/)
solves this: it opens a secure public tunnel to your local port and gives you an
HTTPS URL that forwards straight to the server.

```bash
# in one terminal: run the server
uv run rag_server.py

# in another: expose port 8000
ngrok http 8000
```

ngrok prints a public URL like `https://abcd-1234.ngrok-free.app`. Your MCP
endpoint is then:

```
https://abcd-1234.ngrok-free.app/mcp
```

That's the URL you register in a remote client. (The tunnel URL changes every
restart on the free plan — update the client when it does.)

## Connecting it to an agent

### HuggingFace chat

I tested the server in a **HuggingFace chat** by adding it as a remote MCP server
and pointing it at the ngrok URL (`https://<your-tunnel>.ngrok-free.app/mcp`).
Once connected, the chat lists the four tools and calls `query_documents` on its
own whenever a question needs the indexed documents.

### VS Code

```json
{
  "servers": {
    "rag": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

### Claude Code (CLI)

```bash
claude mcp add --transport http rag http://127.0.0.1:8000/mcp
claude mcp list      # should show "rag ✓ connected"
```

For stdio-only clients, flip the last line of `rag_server.py` to
`mcp.run("stdio")` and let the client launch the script directly.

## Tools reference

### `ingest_data_directory()`
Drops the existing collection and rebuilds it from every file in the data
directory. Parses `.pdf/.docx/.pptx/.doc/.ppt` via LlamaParse, chunks at ~8 000
chars, and stores the chunks in ChromaDB. Returns the final document count.

### `query_documents(query: str, n_results: int = 5)`
Embeds the query and returns the `n_results` most similar chunks, each with its
content, source `file_name`, and a similarity score.

### `list_ingested_files()`
Lists the unique source files in the database and the total number of chunks.

### `server_status()`
Returns the resolved data directory, DB directory, ingested-file count, and a
masked view of the LlamaParse key — handy for verifying configuration.

## Notes

- ChromaDB persists to disk (`./chroma`), so the index survives restarts; rerun
  `ingest_data_directory` after changing the contents of `./data`.
- Embeddings are computed locally by ChromaDB's default model — only document
  **parsing** calls out to LlamaParse.
- Before any real deployment, put this behind auth/HTTPS rather than a raw ngrok
  tunnel.
