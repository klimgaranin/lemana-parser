import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from lemana_parser.config import CONFIG
from lemana_parser.ssl_config import _copy_certifi_to_ascii_path, get_ssl_verify


class SslConfigTests(unittest.TestCase):
    def setUp(self):
        self.original_ssl_verify = CONFIG["ssl_verify"]
        get_ssl_verify.cache_clear()

    def tearDown(self):
        CONFIG["ssl_verify"] = self.original_ssl_verify
        get_ssl_verify.cache_clear()

    def test_returns_false_when_ssl_verify_disabled(self):
        CONFIG["ssl_verify"] = False

        self.assertFalse(get_ssl_verify())

    def test_copies_certifi_bundle_to_ascii_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_dir = tmp_path / "проект"
            source_dir.mkdir()
            source = source_dir / "cacert.pem"
            source.write_text("CERT", encoding="utf-8")
            program_data = tmp_path / "ProgramData"

            with patch(
                "lemana_parser.ssl_config._windows_ca_candidates",
                return_value=[program_data / "lemana-parser" / "cacert.pem"],
            ):
                verify = _copy_certifi_to_ascii_path(source)

            self.assertTrue(str(verify).endswith("lemana-parser/cacert.pem"))
            self.assertTrue(Path(verify).exists())
            self.assertEqual(Path(verify).read_text(encoding="utf-8"), "CERT")

    def test_windows_get_ssl_verify_uses_ascii_copy(self):
        CONFIG["ssl_verify"] = True
        fake_certifi = types.SimpleNamespace(where=lambda: "C:/проект/.venv/certifi/cacert.pem")

        with (
            patch("lemana_parser.ssl_config.os.name", "nt"),
            patch.dict(sys.modules, {"certifi": fake_certifi}),
            patch(
                "lemana_parser.ssl_config._copy_certifi_to_ascii_path",
                return_value="C:/ProgramData/lemana-parser/cacert.pem",
            ),
        ):
            verify = get_ssl_verify()

        self.assertEqual(verify, "C:/ProgramData/lemana-parser/cacert.pem")


if __name__ == "__main__":
    unittest.main()
