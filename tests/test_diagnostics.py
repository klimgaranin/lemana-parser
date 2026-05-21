import tempfile
import unittest
from unittest.mock import patch

from lemana_parser.diagnostics import check_cookie


class CookieDiagnosticsTests(unittest.TestCase):
    def test_read_raw_cookie_from_env_strips_quotes(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as file:
            file.write('LEMANA_COOKIE="a=b; c=d#kept"\n')
            env_path = file.name

        self.assertEqual(check_cookie._read_raw_cookie_from_env(env_path), "a=b; c=d#kept")

    def test_main_returns_config_error_code(self):
        with patch(
            "lemana_parser.diagnostics.check_cookie.validate_config",
            side_effect=check_cookie.ConfigError("bad config"),
        ):
            exit_code = check_cookie.main([])

        self.assertEqual(exit_code, 1)

    def test_main_returns_zero_when_diagnostics_complete(self):
        with (
            patch("lemana_parser.diagnostics.check_cookie.validate_config"),
            patch(
                "lemana_parser.diagnostics.check_cookie._read_raw_cookie_from_env",
                return_value="a=b",
            ),
            patch("lemana_parser.diagnostics.check_cookie._print_env_diagnostics"),
            patch("lemana_parser.diagnostics.check_cookie._print_cookie_parts"),
            patch("lemana_parser.diagnostics.check_cookie._print_response_diagnostics"),
        ):
            exit_code = check_cookie.main([])

        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
