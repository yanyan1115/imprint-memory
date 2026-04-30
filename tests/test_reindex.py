import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


_TMP = tempfile.TemporaryDirectory()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["IMPRINT_DATA_DIR"] = _TMP.name
os.environ["IMPRINT_DB"] = os.path.join(_TMP.name, "memory.db")
os.environ["EMBED_PROVIDER"] = "openai"
os.environ["OPENAI_API_KEY"] = ""

from memo_clover import db as db_mod  # noqa: E402
from memo_clover import memory_manager as mm  # noqa: E402


mm._embed = lambda _text: None


def _reset_database():
    db = db_mod._get_db()
    try:
        for table in (
            "memory_vectors",
            "bank_chunks",
            "conversation_log",
            "memories",
        ):
            db.execute(f"DELETE FROM {table}")
        db.commit()
    finally:
        db.close()


def _count(table: str) -> int:
    con = sqlite3.connect(str(db_mod.DB_PATH))
    try:
        return con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        con.close()


def _match_count(table: str, query: str) -> int:
    con = sqlite3.connect(str(db_mod.DB_PATH))
    try:
        return con.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {table} MATCH ?",
            (query,),
        ).fetchone()[0]
    finally:
        con.close()


class ReindexTests(unittest.TestCase):
    def setUp(self):
        _reset_database()
        mm.BANK_DIR.mkdir(parents=True, exist_ok=True)
        for path in mm.BANK_DIR.glob("*.md"):
            path.unlink()

    def test_reindex_restores_memory_and_conversation_fts(self):
        mm.remember("SQLite FTS5 检索 recovery sample", category="facts")
        db = db_mod._get_db()
        try:
            db.execute(
                """INSERT INTO conversation_log
                   (platform, direction, speaker, content, session_id, entrypoint, created_at, summary)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "telegram",
                    "in",
                    "User",
                    "Telegram SQLite FTS5 检索 conversation sample",
                    "",
                    "test",
                    db_mod.now_str(),
                    "",
                ),
            )
            db.execute("DELETE FROM memories_fts")
            db.execute("DELETE FROM conversation_log_fts")
            db.commit()
        finally:
            db.close()

        self.assertEqual(_match_count("memories_fts", "SQLite"), 0)
        self.assertEqual(_match_count("conversation_log_fts", "SQLite"), 0)

        report = mm.reindex_embeddings()

        self.assertIn("memory_reindex completed: success", report)
        self.assertIn("memories_fts: ok, rebuilt 1 rows", report)
        self.assertIn("conversation_log_fts: ok, rebuilt 1 rows", report)
        self.assertIn("bank_chunks: ok", report)
        self.assertEqual(_match_count("memories_fts", "SQLite"), 1)
        self.assertEqual(_match_count("conversation_log_fts", "SQLite"), 1)

        results = mm.unified_search("SQLite FTS5 检索", pools=["memory", "conversation"])
        pools = {r["pool"] for r in results}
        self.assertIn("memory", pools)
        self.assertIn("conversation", pools)

    def test_reindex_forces_bank_chunks_rebuild(self):
        bank_file = mm.BANK_DIR / "recovery.md"
        bank_file.write_text(
            "# Recovery\n\n## SQLite FTS5 检索\nbank chunk recovery sample\n",
            encoding="utf-8",
        )

        db = db_mod._get_db()
        try:
            db.execute(
                """INSERT INTO bank_chunks
                   (file_path, chunk_text, embedding, file_mtime, index_version)
                   VALUES (?, ?, ?, ?, ?)""",
                (str(bank_file), "stale chunk", None, bank_file.stat().st_mtime, 1),
            )
            db.commit()
        finally:
            db.close()

        report = mm.reindex_embeddings()

        self.assertIn("bank_chunks: ok, cleared 1 rows", report)
        con = sqlite3.connect(str(db_mod.DB_PATH))
        try:
            rows = con.execute("SELECT chunk_text, index_version FROM bank_chunks").fetchall()
        finally:
            con.close()
        self.assertEqual(len(rows), 1)
        self.assertIn("bank chunk recovery sample", rows[0][0])
        self.assertEqual(rows[0][1], mm.BANK_INDEX_VERSION)


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        _TMP.cleanup()
