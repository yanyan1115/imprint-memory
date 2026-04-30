# MemoClover

MemoClover is a standalone long-term memory core for Claude. It gives Claude Code and other MCP clients a durable memory layer backed by SQLite, hybrid retrieval, daily logs, a knowledge bank, conversation search, a message bus, and a small task queue.

It can run by itself as a local MCP server, or as the memory engine inside the larger [Claude Imprint](https://github.com/Qizhan7/claude-imprint) framework.

## What It Does

- Stores durable memories with category, source, importance, emotion, tags, and graph edges.
- Searches across memories, Markdown bank files, and conversation logs with FTS5, vector retrieval, exact matching, and RRF fusion.
- Supports Chinese/Japanese/Korean search through CJK segmentation for FTS5.
- Keeps daily logs and an auto-generated `MEMORY.md` index.
- Provides conversation search for multi-channel history.
- Exposes a message bus for cross-service coordination.
- Queues Claude Code tasks for asynchronous execution.
- Runs in stdio mode for Claude Code or HTTP mode for Claude.ai connector deployments.

All state lives in one SQLite database with WAL enabled. MemoClover is designed to stay simple enough for a small personal server while still giving Claude a serious retrieval backbone.

## Installation

Install from GitHub:

```bash
pip install git+https://github.com/Qizhan7/MemoClover.git
```

Or clone and install locally:

```bash
git clone https://github.com/Qizhan7/MemoClover.git
cd MemoClover
pip install -e .
```

For HTTP mode, include the optional dependencies:

```bash
pip install "memo-clover[http]"
```

## Claude Code MCP Setup

Register MemoClover as a user-level MCP server:

```bash
claude mcp add -s user memo-clover -- memo-clover
```

The server can also be launched directly:

```bash
memo-clover
```

## HTTP Mode

Run the MCP server over HTTP for tunnel or connector deployments:

```bash
memo-clover --http
```

The HTTP endpoint listens on:

```text
http://0.0.0.0:8000/mcp
```

OAuth credentials are read from `~/.imprint-oauth.json` first, then from environment variables:

- `OAUTH_CLIENT_ID`
- `OAUTH_CLIENT_SECRET`
- `OAUTH_ACCESS_TOKEN`

The `~/.imprint-oauth.json` filename is kept for compatibility with existing Claude Imprint deployments.

## MCP Tools

| Tool | Purpose |
|---|---|
| `memory_remember` | Store a memory with category, source, importance, valence, and arousal. |
| `memory_search` | Search memories, knowledge bank chunks, and conversation logs with unified retrieval. |
| `memory_list` | List recent active memories. |
| `memory_update` | Update memory content and metadata by ID. |
| `memory_delete` | Delete a single memory by ID. |
| `memory_forget` | Delete memories containing a keyword. |
| `memory_pin` / `memory_unpin` | Protect or unprotect memories from time decay. |
| `memory_add_tags` | Add structured tags to a memory. |
| `memory_add_edge` | Link two memories with a typed relationship. |
| `memory_get_graph` | Inspect tags, edges, and neighboring memories. |
| `memory_find_duplicates` | Audit semantically similar memory pairs. |
| `memory_find_stale` | Find old or low-activity memories. |
| `memory_decay` | Apply emotional time-decay logic, dry-run by default. |
| `memory_reindex` | Rebuild vectors, FTS tables, and knowledge bank chunks. |
| `memory_daily_log` | Append text to the current daily log. |
| `conversation_search` | Search conversation history. |
| `search_telegram` | Search Telegram and heartbeat conversations. |
| `search_channel` | Search any named conversation channel. |
| `message_bus_read` / `message_bus_post` | Read and write the shared message bus. |
| `cc_execute` | Submit a Claude Code task. |
| `cc_check` / `cc_tasks` | Check or list queued tasks. |

## Configuration

MemoClover intentionally keeps the existing `IMPRINT_*` environment variables for backward compatibility. Existing Claude Imprint users can upgrade without moving their data directory.

| Variable | Default | Description |
|---|---|---|
| `IMPRINT_DATA_DIR` | `~/.imprint` | Base directory for database, logs, generated index, and bank files. |
| `IMPRINT_DB` | `$IMPRINT_DATA_DIR/memory.db` | Explicit SQLite database path. |
| `TZ_OFFSET` | `0` | Fixed UTC hour offset used by timestamps. |
| `EMBED_PROVIDER` | `ollama` | Embedding provider, usually `ollama` or `openai`. |
| `EMBED_MODEL` | provider default | Embedding model name. |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama endpoint. |
| `OPENAI_API_KEY` | empty | API key for OpenAI-compatible embeddings. |
| `EMBED_API_BASE` | `https://api.openai.com` | Base URL for OpenAI-compatible embedding APIs. |
| `IMPRINT_LOCALE` | `en` | Search result labels; use `zh` for Chinese labels. |
| `IMPRINT_BANK_EXCLUDE` | empty | Comma-separated Markdown bank filenames to skip. |

## Embeddings

By default, MemoClover calls Ollama and expects a local embedding model such as `bge-m3`:

```bash
ollama pull bge-m3
ollama serve
```

For OpenAI-compatible embeddings:

```bash
export EMBED_PROVIDER=openai
export OPENAI_API_KEY=sk-...
export EMBED_MODEL=text-embedding-3-small
```

After changing embedding providers or models, call `memory_reindex` to rebuild vector rows and derived search indexes.

If no embedding provider is available, MemoClover falls back to keyword search. Memory remains usable, just less semantic.

## Data Layout

```text
~/.imprint/
|-- memory.db
|-- MEMORY.md
|-- recent_context.md
`-- memory/
    |-- YYYY-MM-DD.md
    `-- bank/
        |-- experience.md
        `-- *.md
```

The `.imprint` directory name is a compatibility promise. MemoClover owns the memory engine; Claude Imprint and other shells can share the same data root.

## Development

Run the core test suite:

```bash
python -m pytest -q
```

Run the server as a module while developing:

```bash
python -m memo_clover.server
python -m memo_clover.server --http
```

Inspect local status with:

```bash
memo-clover-console --status
```

## Relationship To Claude Imprint

MemoClover is the core memory package. It owns the Python API, MCP tools, SQLite schema, indexing, retrieval, summaries, decay logic, and task queue.

Claude Imprint is the full-stack orchestration framework around it. It adds Dashboard, hooks, deployment templates, cron tasks, Telegram utilities, heartbeat automation, Cloudflare Tunnel guidance, and integration tests.

Use MemoClover alone when you want a compact memory engine. Use Claude Imprint when you want the full operating shell.

## Credits

MemoClover was shaped and implemented with help from:

- Anthropic Claude Code
- OpenAI ChatGPT Codex
- Google Gemini

## License

MIT
