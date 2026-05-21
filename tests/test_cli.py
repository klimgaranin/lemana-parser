import unittest
from unittest.mock import Mock, patch

from lemana_parser import cli
from lemana_parser.config import CONFIG


class CliTests(unittest.TestCase):
    def setUp(self):
        self.original_config = dict(CONFIG)

    def tearDown(self):
        CONFIG.clear()
        CONFIG.update(self.original_config)

    def test_no_playwright_requires_cookie(self):
        CONFIG["cookie"] = ""

        with patch("lemana_parser.cli.validate_config"):
            exit_code = cli.main(["--no-playwright", "--no-pause"])

        self.assertEqual(exit_code, 2)

    def test_check_cookie_returns_diagnostic_exit_code(self):
        with patch("lemana_parser.diagnostics.check_cookie.main", return_value=0) as check_main:
            exit_code = cli.main(["--check-cookie", "--no-pause"])

        self.assertEqual(exit_code, 0)
        check_main.assert_called_once_with([])

    def test_cli_overrides_are_applied(self):
        with (
            patch("lemana_parser.cli.validate_config"),
            patch("lemana_parser.cli._run_parsing", new=Mock(return_value="fake-coro")),
            patch("lemana_parser.cli.asyncio.run", return_value=None),
        ):
            exit_code = cli.main(
                [
                    "--no-playwright",
                    "--no-pause",
                    "--cookie",
                    " test_cookie ",
                    "--max-products",
                    "7",
                    "--product-concurrency",
                    "2",
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(CONFIG["cookie"], "test_cookie")
        self.assertEqual(CONFIG["max_products"], 7)
        self.assertEqual(CONFIG["product_concurrency"], 2)


if __name__ == "__main__":
    unittest.main()
