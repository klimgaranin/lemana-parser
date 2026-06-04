import os
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()


class ConfigError(ValueError):
    """Ошибка пользовательской конфигурации."""


Config = dict[str, Any]

_CONFIG_ERRORS: list[str] = []


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError:
        _CONFIG_ERRORS.append(f"{name} должен быть целым числом, сейчас: {value!r}")
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return float(value.replace(",", "."))
    except ValueError:
        _CONFIG_ERRORS.append(f"{name} должен быть числом, сейчас: {value!r}")
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on", "да"}:
        return True
    if normalized in {"0", "false", "no", "n", "off", "нет"}:
        return False
    _CONFIG_ERRORS.append(f"{name} должен быть boolean: true/false, сейчас: {value!r}")
    return default


DEFAULT_CATALOG_URL = (
    "https://lemanapro.ru/catalogue/svetilniki-dlya-vannoy/"
    "?deliveryType=%D0%A1%D0%B0%D0%BC%D0%BE%D0%B2%D1%8B%D0%B2%D0%BE%D0%B7"
    "+%D0%B2+%D0%BC%D0%B0%D0%B3%D0%B0%D0%B7%D0%B8%D0%BD%D0%B5"
)


CONFIG: Config = {
    # ── Целевой каталог ──────────────────────────────────────────────────────
    "catalog_first_page_url": _env_str("LEMANA_CATALOG_URL", DEFAULT_CATALOG_URL),
    # ── Вывод ────────────────────────────────────────────────────────────────
    "output_dir": _env_str("LEMANA_OUTPUT_DIR", "output"),
    "output_filename": _env_str("LEMANA_OUTPUT_FILENAME", "lemana_result.xlsx"),
    # ── Источник данных ─────────────────────────────────────────────────────
    "data_source": _env_str("LEMANA_DATA_SOURCE", "api-fallback"),
    # ── Ограничители ─────────────────────────────────────────────────────────
    "max_products": _env_int("LEMANA_MAX_PRODUCTS", 100000),
    "max_articles": _env_int("LEMANA_MAX_ARTICLES", 0),
    "max_pages_safety": _env_int("LEMANA_MAX_PAGES_SAFETY", 8000),
    # ── Параллелизм ──────────────────────────────────────────────────────────
    "catalog_concurrency": _env_int("LEMANA_CATALOG_CONCURRENCY", 8),
    "product_concurrency": _env_int("LEMANA_PRODUCT_CONCURRENCY", 2),
    # ── Таймауты (секунды) ───────────────────────────────────────────────────
    "catalog_timeout": _env_int("LEMANA_CATALOG_TIMEOUT", 25),
    "product_timeout": _env_int("LEMANA_PRODUCT_TIMEOUT", 30),
    # ── Повторы при ошибке ───────────────────────────────────────────────────
    "max_retries": _env_int("LEMANA_MAX_RETRIES", 4),
    "retry_backoff": _env_float("LEMANA_RETRY_BACKOFF", 0.6),
    # ── Адаптивная пауза между батчами (мс) ─────────────────────────────────
    "min_sleep_ms": _env_int("LEMANA_MIN_SLEEP_MS", 1500),
    "max_sleep_ms": _env_int("LEMANA_MAX_SLEEP_MS", 3500),
    "product_batch_sleep": _env_float("LEMANA_PRODUCT_BATCH_SLEEP", 4.0),
    "product_max_batch_sleep": _env_float("LEMANA_PRODUCT_MAX_BATCH_SLEEP", 10.0),
    "product_adaptive_throttle": _env_bool("LEMANA_PRODUCT_ADAPTIVE_THROTTLE", True),
    "product_recovery_batches": _env_int("LEMANA_PRODUCT_RECOVERY_BATCHES", 6),
    "product_max_active_batch": _env_int("LEMANA_PRODUCT_MAX_ACTIVE_BATCH", 2),
    "product_min_recovery_sleep": _env_float("LEMANA_PRODUCT_MIN_RECOVERY_SLEEP", 4.0),
    "product_deferred_retry": _env_bool("LEMANA_PRODUCT_DEFERRED_RETRY", True),
    "product_deferred_rounds": _env_int("LEMANA_PRODUCT_DEFERRED_ROUNDS", 3),
    "product_deferred_sleep": _env_float("LEMANA_PRODUCT_DEFERRED_SLEEP", 6.0),
    "product_pressure_cooldown": _env_float("LEMANA_PRODUCT_PRESSURE_COOLDOWN", 15.0),
    # ── HTTP fingerprint ────────────────────────────────────────────────────
    "browser_impersonate": _env_str("LEMANA_BROWSER_IMPERSONATE", "chrome"),
    "ssl_verify": _env_bool("LEMANA_SSL_VERIFY", True),
    # ── Cookie recovery ─────────────────────────────────────────────────────
    "cookie_preflight": _env_bool("LEMANA_COOKIE_PREFLIGHT", True),
    "cookie_preflight_product": _env_bool("LEMANA_COOKIE_PREFLIGHT_PRODUCT", True),
    "cookie_auto_refresh": _env_bool("LEMANA_COOKIE_AUTO_REFRESH", True),
    # ── API сайта ───────────────────────────────────────────────────────────
    "api_page_size": _env_int("LEMANA_API_PAGE_SIZE", 60),
    "api_catalog_concurrency": _env_int("LEMANA_API_CATALOG_CONCURRENCY", 1),
    "api_articles_sleep": _env_float("LEMANA_API_ARTICLES_SLEEP", 0.0),
    "api_articles_mode": _env_str("LEMANA_API_ARTICLES_MODE", "strict-then-relaxed"),
    "api_transport": _env_str("LEMANA_API_TRANSPORT", "local"),
    "gas_proxy_url": _env_str("LEMANA_GAS_PROXY_URL", ""),
    "gas_proxy_token": _env_str("LEMANA_GAS_PROXY_TOKEN", ""),
    "api_region_name": _env_str("LEMANA_API_REGION_NAME", "Москва, Московская область"),
    "api_fallback_region_ids": _env_str("LEMANA_API_FALLBACK_REGION_IDS", ""),
    # ── Cookie (Playwright заполняет автоматически) ──────────────────────────
    "cookie": os.getenv("LEMANA_COOKIE", "").strip().strip("\"'"),
}

# Базовые колонки — всегда первые в xlsx
BASE_HEADERS = [
    "Статус",
    "Ошибка",
    "Артикул ЛМ",
    "ССЫЛКА",
    "Наименование товара",
    "Цена на сайте",
    "Ссылка на картинку",
]


def validate_config(config: Config = CONFIG) -> None:
    if _CONFIG_ERRORS:
        raise ConfigError("; ".join(_CONFIG_ERRORS))

    parsed_url = urlparse(config["catalog_first_page_url"])
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ConfigError("LEMANA_CATALOG_URL должен быть полным http/https URL")

    if not config["output_dir"].strip():
        raise ConfigError("LEMANA_OUTPUT_DIR не должен быть пустым")

    if not config["output_filename"].lower().endswith(".xlsx"):
        raise ConfigError("LEMANA_OUTPUT_FILENAME должен оканчиваться на .xlsx")

    if config["data_source"] not in {"html", "api", "api-fallback"}:
        raise ConfigError("LEMANA_DATA_SOURCE должен быть html, api или api-fallback")

    if config["api_articles_mode"] not in {"strict-then-relaxed", "relaxed"}:
        raise ConfigError(
            "LEMANA_API_ARTICLES_MODE должен быть strict-then-relaxed или relaxed"
        )

    if config["api_transport"] not in {"local", "gas", "gas-fallback"}:
        raise ConfigError("LEMANA_API_TRANSPORT должен быть local, gas или gas-fallback")

    if config["api_transport"] in {"gas", "gas-fallback"}:
        parsed_gas_url = urlparse(config["gas_proxy_url"])
        if parsed_gas_url.scheme not in {"http", "https"} or not parsed_gas_url.netloc:
            raise ConfigError(
                "LEMANA_GAS_PROXY_URL должен быть полным URL Web App для транспорта gas"
            )

    positive_int_keys = [
        "max_products",
        "max_pages_safety",
        "catalog_concurrency",
        "product_concurrency",
        "catalog_timeout",
        "product_timeout",
        "max_retries",
        "api_page_size",
        "api_catalog_concurrency",
    ]
    for key in positive_int_keys:
        if config[key] < 1:
            raise ConfigError(f"{key} должен быть >= 1")

    if config["retry_backoff"] <= 0:
        raise ConfigError("LEMANA_RETRY_BACKOFF должен быть > 0")

    if config["product_batch_sleep"] < 0:
        raise ConfigError("LEMANA_PRODUCT_BATCH_SLEEP должен быть >= 0")

    if config["product_max_batch_sleep"] < config["product_batch_sleep"]:
        raise ConfigError(
            "LEMANA_PRODUCT_MAX_BATCH_SLEEP должен быть >= LEMANA_PRODUCT_BATCH_SLEEP"
        )

    if config["product_recovery_batches"] < 1:
        raise ConfigError("LEMANA_PRODUCT_RECOVERY_BATCHES должен быть >= 1")

    if config["product_max_active_batch"] < 1:
        raise ConfigError("LEMANA_PRODUCT_MAX_ACTIVE_BATCH должен быть >= 1")

    if config["product_min_recovery_sleep"] < 0:
        raise ConfigError("LEMANA_PRODUCT_MIN_RECOVERY_SLEEP должен быть >= 0")

    if config["product_deferred_rounds"] < 1:
        raise ConfigError("LEMANA_PRODUCT_DEFERRED_ROUNDS должен быть >= 1")

    if config["product_deferred_sleep"] < 0:
        raise ConfigError("LEMANA_PRODUCT_DEFERRED_SLEEP должен быть >= 0")

    if config["product_pressure_cooldown"] < 0:
        raise ConfigError("LEMANA_PRODUCT_PRESSURE_COOLDOWN должен быть >= 0")

    if config["api_page_size"] < 1 or config["api_page_size"] > 100:
        raise ConfigError("LEMANA_API_PAGE_SIZE должен быть от 1 до 100")

    if config["api_catalog_concurrency"] > 8:
        raise ConfigError("LEMANA_API_CATALOG_CONCURRENCY должен быть от 1 до 8")

    if config["max_articles"] < 0:
        raise ConfigError("LEMANA_MAX_ARTICLES должен быть >= 0")

    if config["api_articles_sleep"] < 0:
        raise ConfigError("LEMANA_API_ARTICLES_SLEEP должен быть >= 0")

    if config["min_sleep_ms"] < 0 or config["max_sleep_ms"] < 0:
        raise ConfigError("LEMANA_MIN_SLEEP_MS и LEMANA_MAX_SLEEP_MS должны быть >= 0")

    if config["min_sleep_ms"] > config["max_sleep_ms"]:
        raise ConfigError("LEMANA_MIN_SLEEP_MS не должен быть больше LEMANA_MAX_SLEEP_MS")


def apply_overrides(**overrides: Any) -> None:
    for key, value in overrides.items():
        if value is not None:
            CONFIG[key] = value
