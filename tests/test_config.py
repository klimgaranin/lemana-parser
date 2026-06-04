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
            "product_max_batch_sleep": 5,
            "product_adaptive_throttle": True,
            "product_recovery_batches": 3,
            "product_max_active_batch": 1,
            "product_min_recovery_sleep": 0,
            "product_deferred_retry": True,
            "product_deferred_rounds": 3,
            "product_deferred_sleep": 0,
            "product_pressure_cooldown": 12,
            "browser_impersonate": "chrome",
            "data_source": "html",
            "max_articles": 0,
            "api_page_size": 60,
            "api_articles_sleep": 0,
            "api_articles_mode": "strict-then-relaxed",
            "api_transport": "local",
            "gas_proxy_url": "",
            "gas_proxy_token": "",
            "api_region_name": "Москва, Московская область",
            "api_fallback_region_ids": "",
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

    def test_rejects_product_max_sleep_below_base_sleep(self):
        with self.assertRaisesRegex(ConfigError, "PRODUCT_MAX_BATCH_SLEEP"):
            validate_config(_valid_config(product_batch_sleep=2, product_max_batch_sleep=1))

    def test_rejects_negative_product_pressure_cooldown(self):
        with self.assertRaisesRegex(ConfigError, "PRESSURE_COOLDOWN"):
            validate_config(_valid_config(product_pressure_cooldown=-1))

    def test_rejects_invalid_deferred_rounds(self):
        with self.assertRaisesRegex(ConfigError, "DEFERRED_ROUNDS"):
            validate_config(_valid_config(product_deferred_rounds=0))

    def test_rejects_invalid_data_source(self):
        with self.assertRaisesRegex(ConfigError, "DATA_SOURCE"):
            validate_config(_valid_config(data_source="broken"))

    def test_rejects_invalid_api_page_size(self):
        with self.assertRaisesRegex(ConfigError, "API_PAGE_SIZE"):
            validate_config(_valid_config(api_page_size=101))

    def test_rejects_negative_api_articles_sleep(self):
        with self.assertRaisesRegex(ConfigError, "API_ARTICLES_SLEEP"):
            validate_config(_valid_config(api_articles_sleep=-1))

    def test_rejects_invalid_api_articles_mode(self):
        with self.assertRaisesRegex(ConfigError, "API_ARTICLES_MODE"):
            validate_config(_valid_config(api_articles_mode="broken"))

    def test_rejects_invalid_api_transport(self):
        with self.assertRaisesRegex(ConfigError, "API_TRANSPORT"):
            validate_config(_valid_config(api_transport="broken"))

    def test_gas_transport_requires_proxy_url(self):
        with self.assertRaisesRegex(ConfigError, "GAS_PROXY_URL"):
            validate_config(_valid_config(api_transport="gas", gas_proxy_url=""))

    def test_gas_transport_accepts_proxy_url(self):
        validate_config(
            _valid_config(
                api_transport="gas",
                gas_proxy_url="https://script.google.com/macros/s/test/exec",
            )
        )

    def test_rejects_negative_max_articles(self):
        with self.assertRaisesRegex(ConfigError, "MAX_ARTICLES"):
            validate_config(_valid_config(max_articles=-1))


if __name__ == "__main__":
    unittest.main()
