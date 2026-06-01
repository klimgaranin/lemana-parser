import os
import tempfile
import time
import unittest
from pathlib import Path

from lemana_parser.api import debug_log
from lemana_parser.config import CONFIG


class ApiDebugLogTests(unittest.TestCase):
    def test_cleanup_removes_old_debug_logs(self):
        old_values = {
            "api_debug_log_enabled": CONFIG["api_debug_log_enabled"],
            "api_debug_log_dir": CONFIG["api_debug_log_dir"],
            "api_debug_log_retention_days": CONFIG["api_debug_log_retention_days"],
        }
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                CONFIG["api_debug_log_enabled"] = True
                CONFIG["api_debug_log_dir"] = tmp_dir
                CONFIG["api_debug_log_retention_days"] = 7
                debug_log._CLEANED = False

                old_file = Path(tmp_dir) / "api_debug_old.jsonl"
                old_file.write_text("old\n", encoding="utf-8")
                old_mtime = time.time() - 8 * 24 * 60 * 60
                os.utime(old_file, (old_mtime, old_mtime))

                debug_log.cleanup_old_api_debug_logs()

                self.assertFalse(old_file.exists())
        finally:
            CONFIG.update(old_values)
            debug_log._CLEANED = False
            debug_log._LOG_PATH = None


if __name__ == "__main__":
    unittest.main()
