import os
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path


_TMP = tempfile.TemporaryDirectory()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["IMPRINT_DATA_DIR"] = _TMP.name
os.environ["IMPRINT_DB"] = os.path.join(_TMP.name, "memory.db")
os.environ["EMBED_PROVIDER"] = "openai"
os.environ["OPENAI_API_KEY"] = ""

from imprint_memory.db import _get_db, now_local  # noqa: E402
from imprint_memory import memory_manager as mm  # noqa: E402


mm._embed = lambda _text: None


def _old_timestamp(days: int = 90) -> str:
    return (now_local() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def _fetch_memory(content: str) -> dict:
    db = _get_db()
    try:
        row = db.execute(
            """SELECT id, content, importance, superseded_by, pinned, decay_rate,
                      arousal, resolved, last_accessed_at
               FROM memories
               WHERE content = ?""",
            (content,),
        ).fetchone()
        if row is None:
            raise AssertionError(f"Memory not found: {content}")
        return dict(row)
    finally:
        db.close()


class Phase3Tests(unittest.TestCase):
    def setUp(self):
        db = _get_db()
        try:
            db.execute("DELETE FROM memory_vectors")
            db.execute("DELETE FROM memories")
            db.commit()
        finally:
            db.close()

    def test_calculate_memory_score_core_has_no_time_decay(self):
        base = {
            "importance": 5,
            "recalled_count": 0,
            "decay_rate": 0.0,
            "arousal": 0.3,
            "resolved": 1,
        }
        old_score = mm.calculate_memory_score({
            **base,
            "created_at": "2000-01-01 00:00:00",
            "last_accessed_at": None,
        })
        recent_score = mm.calculate_memory_score({
            **base,
            "created_at": _old_timestamp(0),
            "last_accessed_at": None,
        })
        self.assertEqual(old_score, recent_score)

    def test_calculate_memory_score_emotion_activation_and_resolution(self):
        base = {
            "importance": 5,
            "recalled_count": 0,
            "decay_rate": 0.05,
            "created_at": _old_timestamp(1),
            "last_accessed_at": None,
        }
        self.assertGreater(
            mm.calculate_memory_score({**base, "arousal": 0.9, "resolved": 0}),
            mm.calculate_memory_score({**base, "arousal": 0.3, "resolved": 0}),
        )
        self.assertGreater(
            mm.calculate_memory_score({
                **base,
                "arousal": 0.3,
                "resolved": 1,
                "recalled_count": 20,
            }),
            mm.calculate_memory_score({**base, "arousal": 0.3, "resolved": 1}),
        )
        self.assertLess(
            mm.calculate_memory_score({**base, "arousal": 0.9, "resolved": 1}),
            mm.calculate_memory_score({**base, "arousal": 0.9, "resolved": 0}),
        )

    def test_decay_memories_dry_run_apply_and_skip_rules(self):
        mm.remember("phase3 archive candidate", category="experience", importance=2)
        mm.remember("phase3 pinned old memory", category="experience", importance=2)
        mm.remember("phase3 core old memory", category="core", importance=2)

        db = _get_db()
        try:
            db.execute(
                """UPDATE memories
                   SET last_accessed_at = ?, decay_rate = 0.1
                   WHERE content IN (?, ?)""",
                (_old_timestamp(90), "phase3 archive candidate", "phase3 pinned old memory"),
            )
            db.execute(
                "UPDATE memories SET pinned = 1 WHERE content = ?",
                ("phase3 pinned old memory",),
            )
            db.execute(
                "UPDATE memories SET last_accessed_at = ?, decay_rate = 0.0 WHERE content = ?",
                (_old_timestamp(90), "phase3 core old memory"),
            )
            db.commit()
        finally:
            db.close()

        preview = mm.decay_memories(dry_run=True, threshold=0.3)
        self.assertEqual(preview["archived"], 1)
        self.assertEqual(preview["details_archived"][0]["content"], "phase3 archive candidate")
        self.assertEqual(_fetch_memory("phase3 archive candidate")["importance"], 2)

        applied = mm.decay_memories(dry_run=False, threshold=0.3)
        self.assertEqual(applied["archived"], 1)
        archived = _fetch_memory("phase3 archive candidate")
        self.assertEqual(archived["importance"], 0)
        self.assertEqual(archived["superseded_by"], -1)

        pinned = _fetch_memory("phase3 pinned old memory")
        self.assertEqual(pinned["importance"], 2)
        self.assertIsNone(pinned["superseded_by"])

        core = _fetch_memory("phase3 core old memory")
        self.assertEqual(core["importance"], 2)
        self.assertIsNone(core["superseded_by"])

    def test_decay_memories_runs_without_candidates(self):
        result = mm.decay_memories(dry_run=False, threshold=0.3)

        self.assertFalse(result["dry_run"])
        self.assertEqual(result["scanned"], 0)
        self.assertEqual(result["archived"], 0)
        self.assertEqual(result["details_archived"], [])

    def test_get_surfacing_memories_filters_and_orders(self):
        mm.remember("phase3 surface me", arousal=0.9, resolved=False)
        mm.remember("phase3 already resolved", arousal=0.9, resolved=True)
        mm.remember("phase3 low arousal unresolved", arousal=0.3, resolved=False)

        surfaced = mm.get_surfacing_memories(limit=3)
        self.assertEqual([m["content"] for m in surfaced], ["phase3 surface me"])
        self.assertEqual(surfaced[0]["arousal"], 0.9)


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        _TMP.cleanup()
