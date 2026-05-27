"""
main.py — Точка входа LemanapPRO Parser v2.

Архитектура event loop на Windows:
  - Playwright sync  → запускается ДО asyncio (нет конфликта)
  - curl_cffi async  → asyncio с WindowsSelectorEventLoopPolicy (требует curl_cffi)
"""

import argparse
import asyncio
import logging
import sys
import time
import warnings
from pathlib import Path

from lemana_parser.auth.playwright_auth import harvest_cookies_sync
from lemana_parser.config import CONFIG, ConfigError, apply_overrides, validate_config
from lemana_parser.models import ProductSummary

PRODUCT_PROFILES = {
    "stable": {
        "product_concurrency": 2,
        "product_batch_sleep": 4.0,
        "product_min_recovery_sleep": 4.0,
        "product_pressure_cooldown": 15.0,
        "product_max_active_batch": 2,
        "product_deferred_sleep": 6.0,
        "product_deferred_rounds": 3,
    },
    "careful": {
        "product_concurrency": 1,
        "product_batch_sleep": 5.0,
        "product_min_recovery_sleep": 5.0,
        "product_pressure_cooldown": 20.0,
        "product_max_active_batch": 1,
        "product_deferred_sleep": 8.0,
        "product_deferred_rounds": 3,
    },
    "fast": {
        "product_concurrency": 2,
        "product_batch_sleep": 2.5,
        "product_min_recovery_sleep": 2.5,
        "product_pressure_cooldown": 15.0,
        "product_max_active_batch": 2,
        "product_deferred_sleep": 5.0,
        "product_deferred_rounds": 2,
    },
}


warnings.filterwarnings(
    "ignore",
    message=r"Curlm alread closed!.*",
    category=UserWarning,
)


class TqdmLoggingHandler(logging.StreamHandler):
    """Пишет логи так, чтобы они не прилипали к progress bar."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            from tqdm import tqdm

            message = self.format(record)
            tqdm.write(message, file=self.stream)
            self.flush()
        except Exception:
            super().emit(record)


# ── Логирование настраиваем до всего остального ──────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        TqdmLoggingHandler(sys.stdout),
        logging.FileHandler("parser.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")


def _log_cookie_setup_help() -> None:
    logger.error("Автообновление cookie не сработало. Можно запустить его отдельно:")
    logger.error(r"  PowerShell: .\get_cookie.bat")
    logger.error(r"  CMD:        get_cookie.bat")
    logger.error(r"После этого проверь cookie: .venv\Scripts\python.exe main.py --check-cookie --no-pause")


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="HTML-парсер каталога lemanapro.ru в Excel.",
    )
    parser.add_argument("--url", help="URL первой страницы каталога")
    parser.add_argument("--output-dir", help="Папка для Excel-файлов")
    parser.add_argument("--output-filename", help="Имя Excel-файла, должно оканчиваться на .xlsx")
    parser.add_argument("--max-products", type=int, help="Максимум товаров для выгрузки")
    parser.add_argument(
        "--data-source",
        choices=["html", "api", "api-fallback"],
        help="Источник данных: html, api или api-fallback",
    )
    parser.add_argument(
        "--articles",
        help="Список артикулов ЛМ через запятую/пробел/перенос строки. Использует API.",
    )
    parser.add_argument(
        "--articles-file",
        help="Файл со списком артикулов ЛМ. Можно разделять запятыми, пробелами или строками.",
    )
    parser.add_argument(
        "--profile",
        choices=sorted(PRODUCT_PROFILES),
        help="Профиль загрузки карточек: stable, careful или fast",
    )
    parser.add_argument(
        "--max-pages-safety", type=int, help="Предохранитель по максимуму страниц каталога"
    )
    parser.add_argument(
        "--catalog-concurrency", type=int, help="Параллельность загрузки страниц каталога"
    )
    parser.add_argument(
        "--product-concurrency", type=int, help="Параллельность загрузки карточек товаров"
    )
    parser.add_argument(
        "--product-batch-sleep", type=float, help="Пауза между батчами карточек, сек"
    )
    parser.add_argument(
        "--product-max-batch-sleep",
        type=float,
        help="Максимальная адаптивная пауза между батчами карточек, сек",
    )
    parser.add_argument(
        "--product-max-active-batch",
        type=int,
        help="Максимальный размер активного батча карточек в адаптивном режиме",
    )
    parser.add_argument(
        "--product-min-recovery-sleep",
        type=float,
        help="Минимальная пауза карточек после восстановления от 403/429, сек",
    )
    parser.add_argument(
        "--product-pressure-cooldown",
        type=float,
        help="Пауза после антибот-сигналов карточек, сек",
    )
    parser.add_argument(
        "--product-deferred-rounds",
        type=int,
        help="Количество медленных раундов повторов для отложенных карточек",
    )
    parser.add_argument(
        "--product-deferred-sleep",
        type=float,
        help="Пауза между отложенными повторами карточек, сек",
    )
    parser.add_argument(
        "--browser-impersonate",
        help="Профиль curl_cffi impersonate, например chrome, chrome124, safari",
    )
    parser.add_argument("--cookie", help="Cookie для запросов, переопределяет LEMANA_COOKIE")
    parser.add_argument(
        "--no-playwright",
        action="store_true",
        help="Не запускать Playwright, использовать только cookie из --cookie/.env",
    )
    parser.add_argument(
        "--check-cookie",
        action="store_true",
        help="Запустить диагностику cookie и завершить работу",
    )
    parser.add_argument("--debug", action="store_true", help="Включить подробное логирование")
    parser.add_argument("--no-pause", action="store_true", help="Не ждать Enter в конце запуска")
    return parser.parse_args(argv)


def _apply_cli_overrides(args: argparse.Namespace) -> None:
    if args.profile:
        apply_overrides(**PRODUCT_PROFILES[args.profile])

    apply_overrides(
        catalog_first_page_url=args.url,
        output_dir=args.output_dir,
        output_filename=args.output_filename,
        data_source=args.data_source,
        max_products=args.max_products,
        max_pages_safety=args.max_pages_safety,
        catalog_concurrency=args.catalog_concurrency,
        product_concurrency=args.product_concurrency,
        product_batch_sleep=args.product_batch_sleep,
        product_max_batch_sleep=args.product_max_batch_sleep,
        product_max_active_batch=args.product_max_active_batch,
        product_min_recovery_sleep=args.product_min_recovery_sleep,
        product_pressure_cooldown=args.product_pressure_cooldown,
        product_deferred_rounds=args.product_deferred_rounds,
        product_deferred_sleep=args.product_deferred_sleep,
        browser_impersonate=args.browser_impersonate,
        cookie=args.cookie.strip().strip("\"'") if args.cookie else None,
    )


def _parse_article_ids(raw: str) -> list[str]:
    import re

    seen: set[str] = set()
    result: list[str] = []
    for article in re.split(r"[\s,;]+", raw or ""):
        article = article.strip()
        if article and article not in seen:
            seen.add(article)
            result.append(article)
    return result


def _load_article_ids(args: argparse.Namespace) -> list[str]:
    raw_parts = []
    if args.articles:
        raw_parts.append(args.articles)
    if args.articles_file:
        path = Path(args.articles_file)
        try:
            raw_parts.append(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ConfigError(f"Не удалось прочитать файл артикулов {path}: {exc}") from exc
    return _parse_article_ids("\n".join(raw_parts))


def _display_data_source(article_ids: list[str]) -> str:
    if article_ids:
        return "api (по артикулам ЛМ)"
    if CONFIG["data_source"] == "api-fallback":
        return "api-fallback (API → HTML fallback)"
    if CONFIG["data_source"] == "api":
        return "api"
    return "html"


async def _run_parsing() -> tuple[str, ProductSummary] | None:
    """Асинхронная часть: curl_cffi каталог + карточки + xlsx."""
    from lemana_parser.catalog import collect_catalog_items
    from lemana_parser.excel_writer import write_xlsx
    from lemana_parser.http_utils import create_session
    from lemana_parser.products import fetch_and_parse_products, summarize_products

    async with create_session() as session:
        logger.info("📄 Шаг 2/3: Сбор каталога...")
        catalog_items = await collect_catalog_items(session)
        logger.info("✅ Товаров в каталоге: %d", len(catalog_items))

        if not catalog_items:
            logger.error("Каталог пуст — проверь URL в config.py")
            return

        logger.info("🔎 Шаг 3/3: Загрузка карточек товаров...")
        products, all_char_keys = await fetch_and_parse_products(session, catalog_items)

    await asyncio.sleep(0)

    logger.info("📝 Запись в Excel...")
    out_path = write_xlsx(products, all_char_keys)
    summary = summarize_products(products)
    logger.info(
        "Итог: всего=%d, успешно=%d, ошибок=%d, статусы=%s",
        summary["total"],
        summary["ok"],
        summary["errors"],
        summary["status_counts"],
    )
    return out_path, summary


async def _run_api_parsing(article_ids: list[str] | None = None) -> tuple[str, ProductSummary] | None:
    """API-first сценарий: пачечные данные товаров без загрузки HTML-карточек."""
    from lemana_parser.api.catalog_api import (
        fetch_catalog_products_api,
        fetch_products_by_articles_api,
    )
    from lemana_parser.excel_writer import write_xlsx
    from lemana_parser.http_utils import create_session
    from lemana_parser.products import summarize_products

    async with create_session() as session:
        if article_ids:
            logger.info("📄 Шаг 2/3: Получаем товары по артикулам ЛМ через API...")
            products, all_char_keys = await fetch_products_by_articles_api(session, article_ids)
        else:
            logger.info("📄 Шаг 2/3: Сбор каталога через API...")
            products, all_char_keys = await fetch_catalog_products_api(session)

    await asyncio.sleep(0)

    logger.info("📝 Запись в Excel...")
    out_path = write_xlsx(products, all_char_keys)
    summary = summarize_products(products)
    logger.info(
        "Итог: всего=%d, успешно=%d, ошибок=%d, статусы=%s",
        summary["total"],
        summary["ok"],
        summary["errors"],
        summary["status_counts"],
    )
    return out_path, summary


def _prepare_cookie_without_playwright() -> bool:
    from lemana_parser.auth.cookie_grabber import CookieGrabberError, harvest_cookie_via_cdp
    from lemana_parser.auth.cookie_health import check_cookie_sync

    cookie = (CONFIG.get("cookie") or "").strip()
    if cookie and CONFIG["cookie_preflight"]:
        check = check_cookie_sync(
            CONFIG["catalog_first_page_url"],
            cookie,
            check_product=CONFIG["cookie_preflight_product"],
        )
        if check.ok:
            if CONFIG["cookie_preflight_product"]:
                logger.info(
                    "🍪 Cookie проверена без Playwright: каталог=%s, карточка=%s",
                    check.catalog_status,
                    check.product_status,
                )
            else:
                logger.info(
                    "🍪 Cookie проверена без Playwright для API: каталог=%s",
                    check.catalog_status,
                )
            return True
        logger.warning("⚠️  Cookie из .env не прошла проверку: %s", check.reason)
    elif cookie:
        logger.info("🍪 Шаг 1/3: Используем cookie без запуска Playwright")
        return True

    if not CONFIG["cookie_auto_refresh"]:
        logger.error("❌ Cookie нет или она не прошла проверку, автообновление отключено")
        _log_cookie_setup_help()
        return False

    logger.info("🔁 Пробуем автоматически получить cookie через Chrome CDP без Playwright...")
    try:
        refreshed = harvest_cookie_via_cdp(CONFIG["catalog_first_page_url"], save=True)
    except CookieGrabberError as exc:
        logger.error("❌ CDP cookie refresh не сработал: %s", exc)
        _log_cookie_setup_help()
        return False

    check = check_cookie_sync(
        CONFIG["catalog_first_page_url"],
        refreshed,
        check_product=CONFIG["cookie_preflight_product"],
    )
    if not check.ok:
        logger.error("❌ Новая cookie не прошла проверку: %s", check.reason)
        _log_cookie_setup_help()
        return False

    CONFIG["cookie"] = refreshed
    logger.info("✅ Cookie автоматически обновлена и проверена")
    return True


def main(argv=None) -> int:
    args = _parse_args(argv)
    _apply_cli_overrides(args)

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    t0 = time.monotonic()

    try:
        validate_config()
        article_ids = _load_article_ids(args)
    except ConfigError as exc:
        logger.error("❌ Ошибка конфигурации: %s", exc)
        return 2

    if article_ids or CONFIG["data_source"] in {"api", "api-fallback"}:
        CONFIG["cookie_preflight_product"] = False

    if args.check_cookie:
        from lemana_parser.diagnostics.check_cookie import main as check_cookie_main

        return check_cookie_main([])

    print("=" * 60)
    print("🚀  LemanapPRO Parser")
    print(f"   URL    : {CONFIG['catalog_first_page_url']}")
    print(f"   Вывод  : {CONFIG['output_dir']}/{CONFIG['output_filename']}")
    print(f"   Данные : {_display_data_source(article_ids)}")
    if article_ids:
        print(f"   Артикулы: {len(article_ids)} шт")
    if args.profile:
        print(f"   Профиль: {args.profile}")
    print(
        "   Карточки: "
        f"batch<={CONFIG['product_max_active_batch']}, "
        f"sleep>={CONFIG['product_min_recovery_sleep']:.1f}s, "
        f"cooldown={CONFIG['product_pressure_cooldown']:.1f}s"
    )
    print("=" * 60)

    # ── Шаг 1: Cookie СИНХРОННО (до event loop) ──────────────────────────────
    if args.no_playwright:
        if not _prepare_cookie_without_playwright():
            return 2
    else:
        logger.info("🌐 Шаг 1/3: Проверяем cookie и при необходимости обновляем...")
        try:
            CONFIG["cookie"] = harvest_cookies_sync(CONFIG["catalog_first_page_url"])
        except Exception as exc:
            logger.error("❌ Playwright упал: %s", exc)
            logger.error("Убедись что установлен браузер: python -m playwright install chromium")
            _log_cookie_setup_help()
            return 1

    # ── Шаг 2+3: curl_cffi с WindowsSelectorEventLoopPolicy ─────────────────
    # SelectorEventLoop нужен curl_cffi (использует add_reader)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        if article_ids:
            result = asyncio.run(_run_api_parsing(article_ids))
        elif CONFIG["data_source"] == "api":
            result = asyncio.run(_run_api_parsing())
        elif CONFIG["data_source"] == "api-fallback":
            try:
                result = asyncio.run(_run_api_parsing())
            except Exception as exc:
                logger.warning("⚠️  API-режим не сработал: %s. Перехожу на HTML fallback.", exc)
                result = asyncio.run(_run_parsing())
        else:
            result = asyncio.run(_run_parsing())
    except Exception as exc:
        logger.exception("❌ Парсер остановлен из-за ошибки: %s", exc)
        return 1

    elapsed = time.monotonic() - t0
    if result:
        out_path, summary = result
        print()
        print("=" * 60)
        print("✨  Готово!")
        print(f"   Файл     : {out_path}")
        print(f"   Товаров  : {summary['total']}")
        print(f"   Успешно  : {summary['ok']}")
        print(f"   Ошибок   : {summary['errors']}")
        if summary["errors"]:
            status_parts = [
                f"{status}={count}"
                for status, count in summary["status_counts"].items()
                if status != "ok"
            ]
            print(f"   Статусы  : {', '.join(status_parts)}")
        print(f"   Время    : {elapsed:.1f} сек")
        print("=" * 60)
        return 0

    return 1
