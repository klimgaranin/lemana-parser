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

        with (
            patch("lemana_parser.cli.validate_config"),
            patch("lemana_parser.cli._prepare_cookie_without_playwright", return_value=False),
        ):
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
            patch("lemana_parser.cli._prepare_cookie_without_playwright", return_value=True),
            patch("lemana_parser.cli._run_parsing", new=Mock(return_value="fake-coro")),
            patch("lemana_parser.cli._run_api_parsing", new=Mock(return_value="fake-api-coro")),
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
                    "--api-articles-sleep",
                    "3",
                    "--api-page-size",
                    "100",
                    "--api-articles-mode",
                    "relaxed",
                    "--max-articles",
                    "10",
                    "--data-source",
                    "api-fallback",
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(CONFIG["cookie"], "test_cookie")
        self.assertEqual(CONFIG["max_products"], 7)
        self.assertEqual(CONFIG["product_concurrency"], 2)
        self.assertEqual(CONFIG["api_articles_sleep"], 3.0)
        self.assertEqual(CONFIG["api_page_size"], 100)
        self.assertEqual(CONFIG["api_articles_mode"], "relaxed")
        self.assertEqual(CONFIG["max_articles"], 10)
        self.assertEqual(CONFIG["data_source"], "api-fallback")

    def test_parse_article_ids_accepts_common_separators(self):
        article_ids = cli._parse_article_ids("123, 456\n789;123")

        self.assertEqual(article_ids, ["123", "456", "789"])

    def test_load_article_ids_applies_max_articles_after_deduplication(self):
        CONFIG["max_articles"] = 2
        args = cli._parse_args(["--articles", "123, 456, 123, 789"])

        article_ids = cli._load_article_ids(args)

        self.assertEqual(article_ids, ["123", "456"])

    def test_display_data_source_for_articles_is_api(self):
        CONFIG["data_source"] = "html"

        self.assertEqual(cli._display_data_source(["123"]), "api (по артикулам ЛМ)")

    def test_display_data_source_for_api_fallback_is_explicit(self):
        CONFIG["data_source"] = "api-fallback"

        self.assertEqual(cli._display_data_source([]), "api-fallback (API → HTML fallback)")

    def test_profile_applies_product_settings(self):
        args = cli._parse_args(["--profile", "careful"])

        cli._apply_cli_overrides(args)

        self.assertEqual(CONFIG["product_concurrency"], 1)
        self.assertEqual(CONFIG["product_max_active_batch"], 1)
        self.assertEqual(CONFIG["product_batch_sleep"], 5.0)
        self.assertEqual(CONFIG["product_pressure_cooldown"], 20.0)

    def test_explicit_cli_overrides_profile(self):
        args = cli._parse_args(
            [
                "--profile",
                "careful",
                "--product-concurrency",
                "2",
                "--product-batch-sleep",
                "4",
                "--product-pressure-cooldown",
                "15",
            ]
        )

        cli._apply_cli_overrides(args)

        self.assertEqual(CONFIG["product_concurrency"], 2)
        self.assertEqual(CONFIG["product_batch_sleep"], 4.0)
        self.assertEqual(CONFIG["product_pressure_cooldown"], 15.0)


if __name__ == "__main__":
    unittest.main()
