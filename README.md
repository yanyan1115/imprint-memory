# imprint-memory

Persistent memory system for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Gives Claude long-term memory that survives across conversations.

Built as an [MCP server](https://modelcontextprotocol.io/) — works with Claude Code locally (stdio) or remotely via HTTP with OAuth.

## What it does

- **Memory CRUD** — store, search, list, and delete memories
- **Hybrid search** — FTS5 keyword search + bge-m3 vector embeddings + time decay scoring
- **Daily logs** — append-only daily journal files
- **Message bus** — shared message log across sources
- **Task queue** — submit tasks for Claude Code to execute asynchronously
- **Bank files** — auto-indexes markdown files in a `bank/` directory for semantic search

All data stored in a single SQLite database with WAL mode for concurrent access.

## Quick start

### 1. Install

```bash
pip install git+https://github.com/Qizhan7/imprint-memory.git
```

Or clone and install locally:

```bash
git clone https://github.com/Qizhan7/imprint-memory.git
cd imprint-memory
pip install -e .
```

### 2. Register with Claude Code

Add to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "imprint-memory": {
      "command": "imprint-memory"
    }
  }
}
```

Or run directly:

```json
{
  "mcpServers": {
    "imprint-memory": {
      "command": "python3",
      "args": ["/path/to/imprint-memory/imprint_memory/server.py"]
    }
  }
}
```

### 3. Use

Claude Code will automatically have access to these tools:

| Tool | Description |
|------|-------------|
| `memory_remember` | Store a memory (with category, source, importance) |
| `memory_search` | Hybrid search across all memories |
| `memory_forget` | Delete memories by keyword |
| `memory_list` | List recent memories |
| `memory_daily_log` | Append to today's log |
| `message_bus_read` | Read recent message bus history |
| `message_bus_post` | Write to the message bus |
| `conversation_search` | Search conversation history by keyword |
| `memory_reindex` | Rebuild all embeddings (after switching providers) |
| `cc_execute` | Submit a task for Claude Code |
| `cc_check` | Check task status |
| `cc_tasks` | List recent tasks |

## Configuration

All configuration via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `IMPRINT_DATA_DIR` | `~/.imprint/` | Base directory for all data |
| `IMPRINT_DB` | `$IMPRINT_DATA_DIR/memory.db` | SQLite database path |
| `TZ_OFFSET` | `0` | Hours offset from UTC (e.g., `12` for NZST) |
| `EMBED_PROVIDER` | `ollama` | Embedding provider: `ollama` or `openai` |
| `EMBED_MODEL` | auto | Model name (defaults: `bge-m3` for ollama, `text-embedding-3-small` for openai) |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API endpoint |
| `OPENAI_API_KEY` | — | API key for OpenAI-compatible providers |
| `EMBED_API_BASE` | `https://api.openai.com` | Base URL for OpenAI-compatible API |
| `MESSAGE_BUS_LIMIT` | `40` | Max messages in the bus (rolling window) |

### Embedding providers

**Option A: Ollama (local, default)** — Free, private, requires local GPU/CPU.

```bash
ollama pull bge-m3
ollama serve
```

**Option B: OpenAI API** — No local GPU needed, pay-per-use.

```bash
export EMBED_PROVIDER=openai
export OPENAI_API_KEY=sk-...
```

**Option C: Any OpenAI-compatible API** — Works with Voyage AI, Azure OpenAI, Google Gemini, etc.

```bash
export EMBED_PROVIDER=openai
export OPENAI_API_KEY=your-api-key
export EMBED_API_BASE=https://your-provider.com  # e.g., https://api.voyageai.com
export EMBED_MODEL=your-model-name               # e.g., voyage-3-lite
```

**No embedding provider?** The system falls back to FTS5 keyword search only — still functional, just less semantic.

**Switching providers:** After switching, run the `memory_reindex` tool to rebuild embeddings with the new provider.

### Bank files

Put markdown files in `$IMPRINT_DATA_DIR/memory/bank/` and they'll be automatically chunked, embedded, and included in search results. Useful for storing structured knowledge (preferences, relationships, experiences).

## HTTP mode (remote access)

For use with Claude.ai through a tunnel:

```bash
imprint-memory --http
# or
pip install imprint-memory[http]
imprint-memory --http
```

Serves on `http://0.0.0.0:8000/mcp` with OAuth 2.0 support.

Configure OAuth credentials via `~/.imprint-oauth.json`:

```json
{
  "client_id": "your-client-id",
  "client_secret": "your-client-secret",
  "access_token": "your-access-token"
}
```

Or via environment variables: `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, `OAUTH_ACCESS_TOKEN`.

### Cloud server deployment

Run imprint-memory on a cloud server for 24/7 access:

```bash
# 1. Install on your server
pip install git+https://github.com/Qizhan7/imprint-memory.git[http]

# 2. Set up embedding (choose one)
export EMBED_PROVIDER=openai
export OPENAI_API_KEY=sk-...
# Or skip for keyword-only search

# 3. Start HTTP server
imprint-memory --http
# Listens on 0.0.0.0:8000

# 4. Expose via Cloudflare Tunnel (recommended) or Nginx + HTTPS
cloudflared tunnel --url http://localhost:8000
```

Then in Claude Code on your local machine, add the remote MCP server URL.

## Data storage

```
~/.imprint/
├── memory.db          # SQLite database (memories, vectors, tasks, bus)
├── MEMORY.md          # Auto-generated memory index
└── memory/
    ├── 2026-03-29.md  # Daily log files
    └── bank/
        ├── experience.md
        └── preferences.md
```

## Console

Check system status at a glance:

```bash
imprint-console            # status + live log
imprint-console --status   # status snapshot only
```

Shows: database stats, Ollama status, data files, HTTP server status.

## Context compression (optional)

If you maintain a rolling context file (e.g. `recent_context.md`), you can compress older messages with a local Ollama model:

```bash
python3 -m imprint_memory.compress /path/to/recent_context.md
```

Configure via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `COMPRESS_MODEL` | `qwen3:8b` | Ollama model for summarization |
| `COMPRESS_KEEP` | `30` | Recent lines to keep as-is |
| `COMPRESS_THRESHOLD` | `50` | Line count that triggers compression |

If Ollama is unavailable, falls back to truncation (keeps only the most recent lines).

## Part of Claude Imprint

This is the core memory module extracted from [claude-imprint](https://github.com/Qizhan7/claude-imprint), a self-hosted AI agent system. It works standalone or as part of the full imprint stack.

## License

MIT
