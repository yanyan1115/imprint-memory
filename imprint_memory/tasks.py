"""
CC remote task queue.
Submit tasks for local Claude Code to execute asynchronously.
Supports session resumption for multi-turn conversations.
"""

import json
import os
import shutil
import subprocess
import threading

from .db import _get_db, now_str
from .bus import bus_post


def submit_task(prompt: str, source: str = "chat", session_id: str = "") -> dict:
    """Submit a task for CC to execute (async). Pass session_id to resume a previous session."""
    db = _get_db()
    db.execute(
        "INSERT INTO cc_tasks (prompt, status, source, session_id, created_at) VALUES (?, 'pending', ?, ?, ?)",
        (prompt, source, session_id, now_str()),
    )
    task_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.commit()
    db.close()

    t = threading.Thread(target=_execute_task, args=(task_id, prompt, session_id), daemon=True)
    t.start()

    return {"task_id": task_id, "status": "pending", "message": f"Task submitted (ID: {task_id}), CC is running"}


def check_task(task_id: int) -> dict:
    """Check task status and result."""
    db = _get_db()
    row = db.execute(
        "SELECT id, prompt, status, result, session_id, created_at, started_at, completed_at FROM cc_tasks WHERE id = ?",
        (task_id,),
    ).fetchone()
    db.close()
    if not row:
        return {"error": f"Task {task_id} not found"}
    return {
        "task_id": row["id"],
        "prompt": row["prompt"][:100] + ("..." if len(row["prompt"]) > 100 else ""),
        "status": row["status"], "result": row["result"],
        "session_id": row["session_id"],
        "created_at": row["created_at"], "started_at": row["started_at"],
        "completed_at": row["completed_at"],
    }


def list_tasks(limit: int = 10) -> list[dict]:
    """List recent tasks."""
    db = _get_db()
    rows = db.execute(
        "SELECT id, prompt, status, session_id, created_at, completed_at FROM cc_tasks ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    db.close()
    return [{
        "task_id": r["id"],
        "prompt": r["prompt"][:80] + ("..." if len(r["prompt"]) > 80 else ""),
        "status": r["status"], "session_id": r["session_id"],
        "created_at": r["created_at"], "completed_at": r["completed_at"],
    } for r in rows]


def _execute_task(task_id: int, prompt: str, session_id: str = ""):
    """Execute a CC task in background (subprocess)."""
    db = _get_db()
    db.execute("UPDATE cc_tasks SET status = 'running', started_at = ? WHERE id = ?", (now_str(), task_id))
    db.commit()
    db.close()

    claude_bin = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")
    env = {**os.environ}
    env.pop("CLAUDECODE", None)
    env["PATH"] = os.path.expanduser("~/.local/bin") + ":" + os.path.expanduser("~/.bun/bin") + ":" + env.get("PATH", "")

    try:
        cmd = [claude_bin, "-p", prompt, "--permission-mode", "auto",
               "--output-format", "json", "--max-budget-usd", "1.00"]

        if session_id:
            cmd.extend(["--resume", session_id])

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300, env=env,
        )

        # Parse JSON output to extract session_id
        new_session_id = ""
        output_text = ""

        if result.returncode != 0:
            stderr_msg = result.stderr.strip()
            output_text = f"Process exited with code {result.returncode}"
            if stderr_msg:
                output_text += f": {stderr_msg}"
            elif result.stdout.strip():
                output_text += f"\n{result.stdout.strip()}"
            status = "error"
        else:
            raw = result.stdout.strip()
            try:
                parsed = json.loads(raw)
                new_session_id = parsed.get("session_id", "")
                output_text = parsed.get("result", raw)
            except json.JSONDecodeError:
                output_text = raw or result.stderr.strip() or "(no output)"
            status = "completed"

    except subprocess.TimeoutExpired:
        output_text = "Task timed out (5 minutes)"
        status = "timeout"
        new_session_id = ""
    except Exception as e:
        output_text = f"Execution error: {str(e)}"
        status = "error"
        new_session_id = ""

    db = _get_db()
    db.execute(
        "UPDATE cc_tasks SET status = ?, result = ?, session_id = ?, completed_at = ? WHERE id = ?",
        (status, output_text, new_session_id or session_id, now_str(), task_id),
    )
    db.commit()
    db.close()

    summary = output_text[:100] if len(output_text) <= 100 else output_text[:97] + "..."
    bus_post("cc_task", "out", f"[Task#{task_id} {status}] {summary}")
