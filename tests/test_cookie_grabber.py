import tempfile
import unittest
from pathlib import Path

from lemana_parser.auth import cookie_grabber


class CookieGrabberTests(unittest.TestCase):
    def test_format_site_cookies_keeps_only_target_domain(self):
        cookie_str = cookie_grabber._format_site_cookies(
            [
                {"domain": ".lemanapro.ru", "path": "/", "name": "qrator_jsid2", "value": "abc"},
                {"domain": "example.com", "path": "/", "name": "session", "value": "skip"},
                {"domain": "lemanapro.ru", "path": "/", "name": "region", "value": "moscow"},
            ]
        )

        self.assertEqual(cookie_str, "qrator_jsid2=abc; region=moscow")

    def test_save_cookie_to_env_replaces_existing_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text(
                'LEMANA_OUTPUT_DIR="output"\nLEMANA_COOKIE="old"\n',
                encoding="utf-8",
            )

            cookie_grabber._save_cookie_to_env("qrator_jsid2=new", str(env_path))

            self.assertEqual(
                env_path.read_text(encoding="utf-8"),
                'LEMANA_OUTPUT_DIR="output"\nLEMANA_COOKIE="qrator_jsid2=new"\n',
            )


if __name__ == "__main__":
    unittest.main()
