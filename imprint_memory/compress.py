#!/usr/bin/env python3
"""
Compress old messages in a context file using a local Ollama model.

Can be called standalone or imported as a library.
Designed to keep a rolling context file (e.g. recent_context.md) from growing
unbounded by summarizing older messages with a local LLM.

Usage:
    python3 -m imprint_memory.compress /path/to/recent_context.md

Environment variables:
    OLLAMA_URL       — Ollama API endpoint (default: http://localhost:11434)
    COMPRESS_MODEL   — Model to use (default: qwen3:8b)
    COMPRESS_KEEP    — Number of recent lines to keep as-is (default: 30)
    COMPRESS_THRESHOLD — Line count that triggers compression (default: 50)
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
COMPRESS_MODEL = os.environ.get("COMPRESS_MODEL", "qwen3:8b")
KEEP_RECENT = int(os.environ.get("COMPRESS_KEEP", 30))
THRESHOLD = int(os.environ.get("COMPRESS_THRESHOLD", 50))

SYSTEM_PROMPT = (
    "You are a log compressor. "
    "Compress the following log into 3-5 summary lines. "
    "Preserve all topics faithfully. "
    "Keep names, timestamps, decisions, and context. "
    "Output ONLY the summary lines, nothing else."
)


def compress_messages(messages: list[str], model: str = "", ollama_url: str = "") -> str | None:
    """Call local Ollama to summarize messages into 3-5 lines.

    Returns the summary string, or None if Ollama is unavailable.
    """
    text = "\n".join(messages)
    url = ollama_url or OLLAMA_URL
    mdl = model or COMPRESS_MODEL

    try:
        req = urllib.request.Request(
            f"{url}/api/chat",
            data=json.dumps({
                "model": mdl,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Compress this log:\n\n{text}"},
                ],
                "stream": False,
                "think": False,
                "options": {"temperature": 0.3, "num_predict": 500},
            }).encode(),
            headers={"Content-Type": "application/json"},
        )
        resp = json.loads(urllib.request.urlopen(req, timeout=60).read())
        result = resp.get("message", {}).get("content", "").strip()
        lines = [l.strip() for l in result.splitlines() if l.strip()]
        return "\n".join(lines) if lines else None
    except Exception as e:
        print(f"Ollama compression failed: {e}", file=sys.stderr)
        return None


def compress_file(context_file: Path, keep: int = 0, threshold: int = 0) -> bool:
    """Compress a context file in-place. Returns True if compression happened."""
    keep = keep or KEEP_RECENT
    threshold = threshold or THRESHOLD

    if not context_file.exists():
        return False

    content = context_file.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Separate header comments from message lines
    header_lines = []
    message_lines = []
    for line in lines:
        if line.startswith("<!--") or not line.strip():
            header_lines.append(line)
        else:
            message_lines.append(line)

    if len(message_lines) <= threshold:
        print(f"Only {len(message_lines)} messages, below threshold {threshold}", file=sys.stderr)
        return False

    old_messages = message_lines[:-keep]
    recent_messages = message_lines[-keep:]

    print(f"Compressing {len(old_messages)} old messages, keeping {len(recent_messages)} recent", file=sys.stderr)

    summary = compress_messages(old_messages)
    if summary is None:
        print("Compression failed, truncating to recent messages only", file=sys.stderr)
        new_content = "\n".join(header_lines + [""] + recent_messages) + "\n"
    else:
        new_content = "\n".join(header_lines + [""] + [summary, ""] + recent_messages) + "\n"

    # Atomic write
    tmp = context_file.with_suffix(".tmp")
    tmp.write_text(new_content, encoding="utf-8")
    os.replace(str(tmp), str(context_file))

    n = len(summary.splitlines()) if summary else 0
    print(f"Compressed: {len(old_messages)} -> {n} lines", file=sys.stderr)
    return True


def compress_context(context_file: str | Path, keep: int = 0, threshold: int = 0) -> bool:
    """Backward-compatible alias for older callers."""
    return compress_file(Path(context_file), keep=keep, threshold=threshold)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 -m imprint_memory.compress <context_file>", file=sys.stderr)
        sys.exit(1)
    compress_file(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
