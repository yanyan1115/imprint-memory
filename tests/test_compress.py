import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from imprint_memory import compress  # noqa: E402


class CompressCompatibilityTests(unittest.TestCase):
    def test_compress_context_alias_delegates_to_compress_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
            path = Path(f.name)

        try:
            with mock.patch.object(compress, "compress_file", return_value=True) as compress_file:
                result = compress.compress_context(str(path), keep=12, threshold=34)
        finally:
            path.unlink(missing_ok=True)

        self.assertTrue(result)
        compress_file.assert_called_once_with(path, keep=12, threshold=34)


if __name__ == "__main__":
    unittest.main()
