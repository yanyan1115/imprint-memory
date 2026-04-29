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

from imprint_memory.db import _get_db  # noqa: E402
from imprint_memory import memory_manager as mm  # noqa: E402


class SummaryLifecycleTests(unittest.TestCase):
    def setUp(self):
        db = _get_db()
        try:
            db.execute("DELETE FROM summaries")
            db.commit()
        finally:
            db.close()

    def test_save_update_delete_summary_lifecycle(self):
        saved = mm.save_summary(" first summary ", turn_count="3", platform=" telegram ")
        self.assertEqual(saved["status"], "saved")

        summary_id = saved["id"]
        summaries = mm.get_recent_summaries(limit=10)
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["id"], summary_id)
        self.assertEqual(summaries[0]["content"], "first summary")
        self.assertEqual(summaries[0]["turn_count"], 3)
        self.assertEqual(summaries[0]["platform"], "telegram")

        updated = mm.update_summary(
            summary_id,
            content=" refined summary ",
            turn_count=-5,
            platform="",
        )
        self.assertTrue(updated["ok"])

        summaries = mm.get_recent_summaries(limit=10)
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["id"], summary_id)
        self.assertEqual(summaries[0]["content"], "refined summary")
        self.assertEqual(summaries[0]["turn_count"], 0)
        self.assertEqual(summaries[0]["platform"], "unknown")

        deleted = mm.delete_summary(summary_id)
        self.assertTrue(deleted["ok"])
        self.assertEqual(mm.get_recent_summaries(limit=10), [])

    def test_update_and_delete_missing_summary_report_not_found(self):
        updated = mm.update_summary(999, content="missing", turn_count=1, platform="cc")
        deleted = mm.delete_summary(999)

        self.assertFalse(updated["ok"])
        self.assertEqual(updated["error"], "summary not found")
        self.assertFalse(deleted["ok"])
        self.assertEqual(deleted["error"], "summary not found")

    def test_update_rejects_empty_content(self):
        saved = mm.save_summary("summary", turn_count=1, platform="cc")

        result = mm.update_summary(saved["id"], content="   ", turn_count=1, platform="cc")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "content is required")


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        _TMP.cleanup()
