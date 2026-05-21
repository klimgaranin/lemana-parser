import unittest

from lemana_parser.config import CONFIG, ConfigError, validate_config


def _valid_config(**overrides):
    config = dict(CONFIG)
    config.update(
        {
            "catalog_first_page_url": "https://lemanapro.ru/catalogue/test/",
            "output_dir": "output",
            "output_filename": "result.xlsx",
            "max_products": 1,
            "max_pages_safety": 1,
            "catalog_concurrency": 1,
            "product_concurrency": 1,
            "catalog_timeout": 1,
            "product_timeout": 1,
            "max_retries": 1,
            "retry_backoff": 0.1,
            "min_sleep_ms": 0,
            "max_sleep_ms": 100,
            "product_batch_sleep": 0,
        }
    )
    config.update(overrides)
    return config


class ConfigValidationTests(unittest.TestCase):
    def test_valid_config_passes(self):
        validate_config(_valid_config())

    def test_rejects_invalid_url(self):
        with self.assertRaisesRegex(ConfigError, "полным http/https URL"):
            validate_config(_valid_config(catalog_first_page_url="lemanapro.ru/catalogue"))

    def test_rejects_non_xlsx_filename(self):
        with self.assertRaisesRegex(ConfigError, "оканчиваться на .xlsx"):
            validate_config(_valid_config(output_filename="result.csv"))

    def test_rejects_invalid_concurrency(self):
        with self.assertRaisesRegex(ConfigError, "product_concurrency должен быть >= 1"):
            validate_config(_valid_config(product_concurrency=0))

    def test_rejects_invalid_sleep_range(self):
        with self.assertRaisesRegex(ConfigError, "не должен быть больше"):
            validate_config(_valid_config(min_sleep_ms=200, max_sleep_ms=100))


if __name__ == "__main__":
    unittest.main()
