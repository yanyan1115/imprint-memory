import math
import os
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

from memo_clover.db import _get_db, now_str  # noqa: E402
from memo_clover import memory_manager as mm  # noqa: E402


mm._embed = lambda _text: None


def _fetch_memory(content: str) -> dict:
    db = _get_db()
    try:
        row = db.execute(
            """SELECT id, content, category, valence, arousal, resolved, decay_rate
               FROM memories
               WHERE content = ?""",
            (content,),
        ).fetchone()
        if row is None:
            raise AssertionError(f"Memory not found: {content}")
        return dict(row)
    finally:
        db.close()


class Phase2Tests(unittest.TestCase):
    def test_schema_has_emotional_columns(self):
        db = _get_db()
        try:
            columns = {
                row["name"]
                for row in db.execute("PRAGMA table_info(memories)").fetchall()
            }
        finally:
            db.close()

        self.assertTrue(
            {"valence", "arousal", "resolved", "decay_rate"}.issubset(columns)
        )

    def test_remember_writes_emotional_fields_and_decay_rate(self):
        mm.remember("phase2 facts memory", category="facts")
        facts = _fetch_memory("phase2 facts memory")
        self.assertEqual(facts["decay_rate"], 0.0)

        mm.remember(
            "phase2 event unresolved",
            category="events",
            arousal=0.9,
            resolved=False,
        )
        event = _fetch_memory("phase2 event unresolved")
        self.assertEqual(event["decay_rate"], 0.05)
        self.assertEqual(event["resolved"], 0)
        self.assertEqual(event["arousal"], 0.9)

        mm.remember("phase2 default memory")
        default = _fetch_memory("phase2 default memory")
        self.assertEqual(default["valence"], 0.5)
        self.assertEqual(default["arousal"], 0.3)
        self.assertEqual(default["resolved"], 1)

    def test_rerank_emotional_weight_boosts_unresolved_high_arousal(self):
        base = {
            "importance": 5,
            "recalled_count": 0,
            "created_at": now_str(),
            "last_accessed_at": None,
            "pinned": 0,
            "decay_rate": 0.05,
        }
        high_emotion = {**base, "arousal": 0.9, "resolved": 0}
        calm_resolved = {**base, "arousal": 0.3, "resolved": 1}

        self.assertGreater(
            mm._rerank_memory(0.05, high_emotion),
            mm._rerank_memory(0.05, calm_resolved),
        )

    def test_zero_decay_rate_removes_time_decay(self):
        base = {
            "importance": 5,
            "recalled_count": 0,
            "last_accessed_at": None,
            "pinned": 0,
            "decay_rate": 0.0,
            "arousal": 0.3,
            "resolved": 1,
        }
        old_row = {**base, "created_at": "2000-01-01 00:00:00"}
        recent_row = {**base, "created_at": now_str()}

        self.assertTrue(math.isclose(
            mm._rerank_memory(0.05, old_row),
            mm._rerank_memory(0.05, recent_row),
            rel_tol=1e-12,
            abs_tol=1e-12,
        ))

    def test_update_memory_can_mark_resolved(self):
        mm.remember(
            "phase2 update resolved memory",
            category="events",
            arousal=0.8,
            resolved=False,
        )
        row = _fetch_memory("phase2 update resolved memory")
        self.assertEqual(row["resolved"], 0)

        result = mm.update_memory(row["id"], resolved=1)
        self.assertTrue(result["ok"])

        updated = _fetch_memory("phase2 update resolved memory")
        self.assertEqual(updated["resolved"], 1)


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        _TMP.cleanup()
