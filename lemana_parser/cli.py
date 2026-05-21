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

# ── Логирование настраиваем до всего остального ──────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("parser.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")

from lemana_parser.auth.playwright_auth import harvest_cookies_sync
from lemana_parser.config import CONFIG, ConfigError, apply_overrides, validate_config


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="HTML-парсер каталога lemanapro.ru в Excel.",
    )
    parser.add_argument("--url", help="URL первой страницы каталога")
    parser.add_argument("--output-dir", help="Папка для Excel-файлов")
    parser.add_argument("--output-filename", help="Имя Excel-файла, должно оканчиваться на .xlsx")
    parser.add_argument("--max-products", type=int, help="Максимум товаров для выгрузки")
    parser.add_argument("--max-pages-safety", type=int, help="Предохранитель по максимуму страниц каталога")
    parser.add_argument("--catalog-concurrency", type=int, help="Параллельность загрузки страниц каталога")
    parser.add_argument("--product-concurrency", type=int, help="Параллельность загрузки карточек товаров")
    parser.add_argument("--product-batch-sleep", type=float, help="Пауза между батчами карточек, сек")
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
    apply_overrides(
        catalog_first_page_url=args.url,
        output_dir=args.output_dir,
        output_filename=args.output_filename,
        max_products=args.max_products,
        max_pages_safety=args.max_pages_safety,
        catalog_concurrency=args.catalog_concurrency,
        product_concurrency=args.product_concurrency,
        product_batch_sleep=args.product_batch_sleep,
        cookie=args.cookie.strip().strip('"\'') if args.cookie else None,
    )


async def _run_parsing() -> None:
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


def main(argv=None) -> int:
    args = _parse_args(argv)
    _apply_cli_overrides(args)

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    t0 = time.monotonic()

    try:
        validate_config()
    except ConfigError as exc:
        logger.error("❌ Ошибка конфигурации: %s", exc)
        return 2

    if args.check_cookie:
        from lemana_parser.diagnostics.check_cookie import main as check_cookie_main

        check_cookie_main()
        return 0

    print("=" * 60)
    print("🚀  LemanapPRO Parser")
    print(f"   URL    : {CONFIG['catalog_first_page_url']}")
    print(f"   Вывод  : {CONFIG['output_dir']}/{CONFIG['output_filename']}")
    print("=" * 60)

    # ── Шаг 1: Playwright СИНХРОННО (до event loop) ──────────────────────────
    if args.no_playwright:
        if not CONFIG["cookie"]:
            logger.error("❌ --no-playwright требует cookie в --cookie или LEMANA_COOKIE")
            return 2
        logger.info("🍪 Шаг 1/3: Используем cookie без запуска Playwright")
    else:
        logger.info("🌐 Шаг 1/3: Получаем cookie через Playwright...")
        try:
            CONFIG["cookie"] = harvest_cookies_sync(CONFIG["catalog_first_page_url"])
        except Exception as exc:
            logger.error("❌ Playwright упал: %s", exc)
            logger.error("Убедись что установлен браузер: python -m playwright install chromium")
            return 1

    # ── Шаг 2+3: curl_cffi с WindowsSelectorEventLoopPolicy ─────────────────
    # SelectorEventLoop нужен curl_cffi (использует add_reader)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
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
