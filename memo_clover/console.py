#!/usr/bin/env python3
"""
memo-clover console — system status and live log viewer.

Shows memory database stats, Ollama status, and tails the server log.

Usage:
    python3 -m memo_clover.console              # status + live log
    python3 -m memo_clover.console --status      # status snapshot only

Or if installed:
    memo-clover-console
    memo-clover-console --status
"""

import os
import signal
import sqlite3
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .db import DB_PATH, DATA_DIR, DAILY_LOG_DIR, BANK_DIR, MEMORY_INDEX

# ── ANSI Colors ──────────────────────────────────────────────
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
CYAN = "\033[36m"

TZ_OFFSET = int(os.environ.get("TZ_OFFSET", 0))
LOCAL_TZ = timezone(timedelta(hours=TZ_OFFSET))


def now_str() -> str:
    return datetime.now(LOCAL_TZ).strftime("%H:%M:%S")


def check_ollama() -> tuple[bool, list[str]]:
    """Check Ollama status and available models."""
    try:
        import json
        import urllib.request
        url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
        resp = json.loads(urllib.request.urlopen(
            f"{url}/api/tags", timeout=3
        ).read())
        models = [m["name"] for m in resp.get("models", [])]
        return True, models
    except Exception:
        return False, []


def check_db() -> dict:
    """Check memory.db stats."""
    if not DB_PATH.exists():
        return {"exists": False}
    try:
        db = sqlite3.connect(str(DB_PATH), timeout=3)
        db.row_factory = sqlite3.Row
        stats = {}
        for table in ["memories", "conversation_log", "message_bus", "cc_tasks", "daily_logs"]:
            try:
                row = db.execute(f"SELECT COUNT(*) as c FROM {table}").fetchone()
                stats[table] = row["c"]
            except Exception:
                stats[table] = "-"
        # Last memory
        try:
            row = db.execute(
                "SELECT created_at FROM memories ORDER BY id DESC LIMIT 1"
            ).fetchone()
            stats["last_memory"] = row["created_at"] if row else "none"
        except Exception:
            stats["last_memory"] = "?"
        # Last conversation
        try:
            row = db.execute(
                "SELECT created_at FROM conversation_log ORDER BY id DESC LIMIT 1"
            ).fetchone()
            stats["last_conv"] = row["created_at"] if row else "none"
        except Exception:
            stats["last_conv"] = "?"
        db.close()
        stats["exists"] = True
        stats["size_mb"] = round(DB_PATH.stat().st_size / 1024 / 1024, 1)
        return stats
    except Exception as e:
        return {"exists": True, "error": str(e)}


def check_http_server() -> tuple[bool, int | None]:
    """Check if the MCP HTTP server is responding."""
    try:
        import urllib.request
        resp = urllib.request.urlopen("http://localhost:8000/mcp", timeout=2)
        return True, 8000
    except Exception:
        return False, None


def print_status():
    """Print system status panel."""
    ts = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")
    tz_name = f"UTC{'+' if TZ_OFFSET >= 0 else ''}{TZ_OFFSET}"
    print(f"\n{BOLD}{'=' * 55}{RESET}")
    print(f"{BOLD}  MemoClover CONSOLE  {RESET}{DIM}  {ts} {tz_name}{RESET}")
    print(f"{BOLD}{'=' * 55}{RESET}")

    # ── Database ──
    print(f"\n{BOLD}  DATABASE{RESET}  {DIM}{DB_PATH}{RESET}")
    db = check_db()
    if not db.get("exists"):
        print(f"    {RED}  NOT FOUND{RESET}")
    elif db.get("error"):
        print(f"    {RED}  ERROR: {db['error']}{RESET}")
    else:
        print(f"    {GREEN}●{RESET} Size: {db.get('size_mb', '?')} MB")
        print(f"      memories:      {db.get('memories', '-')}")
        print(f"      conversations: {db.get('conversation_log', '-')}")
        print(f"      bus messages:  {db.get('message_bus', '-')}")
        print(f"      tasks:         {db.get('cc_tasks', '-')}")
        print(f"      daily logs:    {db.get('daily_logs', '-')}")
        print(f"      Last memory:       {db.get('last_memory', '?')}")
        print(f"      Last conversation: {db.get('last_conv', '?')}")

    # ── Data Files ──
    print(f"\n{BOLD}  DATA FILES{RESET}  {DIM}{DATA_DIR}{RESET}")
    # MEMORY.md
    if MEMORY_INDEX.exists():
        lines = len(MEMORY_INDEX.read_text(errors="replace").splitlines())
        print(f"    {GREEN}●{RESET} MEMORY.md ({lines} lines)")
    else:
        print(f"    {DIM}○{RESET} MEMORY.md (not created yet)")
    # Daily logs
    if DAILY_LOG_DIR.exists():
        logs = sorted(DAILY_LOG_DIR.glob("*.md"))
        today = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")
        today_log = DAILY_LOG_DIR / f"{today}.md"
        print(f"    {GREEN}●{RESET} Daily logs: {len(logs)} files", end="")
        if today_log.exists():
            print(f"  (today's log exists)")
        else:
            print(f"  {DIM}(no log today yet){RESET}")
    else:
        print(f"    {DIM}○{RESET} Daily logs: directory not created")
    # Bank
    if BANK_DIR.exists():
        bank_files = list(BANK_DIR.glob("*.md"))
        print(f"    {GREEN}●{RESET} Bank files: {len(bank_files)}")
    else:
        print(f"    {DIM}○{RESET} Bank: directory not created")

    # ── Ollama ──
    print(f"\n{BOLD}  OLLAMA{RESET}")
    ollama_ok, models = check_ollama()
    if ollama_ok:
        embed_model = os.environ.get("EMBED_MODEL", "bge-m3")
        has_embed = any(embed_model in m for m in models)
        print(f"    {GREEN}● RUNNING{RESET}  {len(models)} model(s)")
        if has_embed:
            print(f"      {GREEN}●{RESET} Embedding model ({embed_model}) available")
        else:
            print(f"      {YELLOW}!{RESET} Embedding model ({embed_model}) not found — search will use FTS5 only")
        for m in models[:8]:
            print(f"        {DIM}{m}{RESET}")
    else:
        print(f"    {YELLOW}○ OFFLINE{RESET}  (search falls back to FTS5 keyword-only)")

    # ── HTTP Server ──
    print(f"\n{BOLD}  HTTP SERVER{RESET}")
    http_ok, port = check_http_server()
    if http_ok:
        print(f"    {GREEN}● RUNNING{RESET}  on port {port}")
    else:
        print(f"    {DIM}○ NOT RUNNING{RESET}  (stdio mode only)")

    print(f"\n{BOLD}{'─' * 55}{RESET}")


def tail_log(log_path: Path):
    """Tail a log file with colored output."""
    print(f"\n{BOLD}  LIVE LOG{RESET}  {DIM}{log_path}{RESET}")
    print(f"  {DIM}(Ctrl+C to stop){RESET}\n")

    if not log_path.exists():
        print(f"  {DIM}Log file not found, waiting...{RESET}")
        while not log_path.exists():
            time.sleep(1)

    with open(log_path, "r", errors="replace") as f:
        f.seek(0, 2)  # seek to end
        try:
            while True:
                line = f.readline()
                if line:
                    lower = line.lower()
                    if any(kw in lower for kw in ["error", "exception", "traceback", "failed", "timeout"]):
                        print(f"  {RED}{BOLD}{now_str()} {line.rstrip()}{RESET}")
                    elif any(kw in lower for kw in ["warn", "fallback", "skip", "degraded"]):
                        print(f"  {YELLOW}{now_str()} {line.rstrip()}{RESET}")
                    else:
                        print(f"  {DIM}{now_str()}{RESET} {line.rstrip()}")
                else:
                    # Check for file rotation
                    try:
                        if f.tell() > log_path.stat().st_size:
                            f.seek(0)
                    except Exception:
                        pass
                    time.sleep(0.5)
        except KeyboardInterrupt:
            print(f"\n{DIM}  Stopped.{RESET}")


def main():
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    if "--status" in sys.argv:
        print_status()
    else:
        print_status()
        # Try to find a log file to tail
        # Check common locations
        log_candidates = [
            Path.cwd() / "logs" / "http.log",
            DATA_DIR / "logs" / "http.log",
            DATA_DIR / "server.log",
        ]
        log_path = None
        for p in log_candidates:
            if p.exists():
                log_path = p
                break
        if log_path:
            tail_log(log_path)
        else:
            print(f"\n  {DIM}No log file found to tail. Run with --status for status only.{RESET}")


if __name__ == "__main__":
    main()
