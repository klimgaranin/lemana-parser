"""
main.py — Точка входа LemanapPRO Parser v2.

Архитектура event loop на Windows:
  - Playwright sync  → запускается ДО asyncio (нет конфликта)
  - curl_cffi async  → asyncio с WindowsSelectorEventLoopPolicy (требует curl_cffi)
"""
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

from config import CONFIG
from playwright_auth import harvest_cookies_sync


async def _run_parsing() -> None:
    """Асинхронная часть: curl_cffi каталог + карточки + xlsx."""
    from http_utils import create_session
    from catalog import collect_catalog_items
    from products import fetch_and_parse_products
    from excel_writer import write_xlsx

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
    return out_path, len(products)


def main() -> None:
    t0 = time.monotonic()

    print("=" * 60)
    print("🚀  LemanapPRO Parser")
    print(f"   URL    : {CONFIG['catalog_first_page_url']}")
    print(f"   Вывод  : {CONFIG['output_dir']}/{CONFIG['output_filename']}")
    print("=" * 60)

    # ── Шаг 1: Playwright СИНХРОННО (до event loop) ──────────────────────────
    logger.info("🌐 Шаг 1/3: Получаем cookie через Playwright...")
    try:
        CONFIG["cookie"] = harvest_cookies_sync(CONFIG["catalog_first_page_url"])
    except Exception as exc:
        logger.error("❌ Playwright упал: %s", exc)
        logger.error("Убедись что установлен браузер: playwright install chromium")
        return

    # ── Шаг 2+3: curl_cffi с WindowsSelectorEventLoopPolicy ─────────────────
    # SelectorEventLoop нужен curl_cffi (использует add_reader)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    result = asyncio.run(_run_parsing())

    elapsed = time.monotonic() - t0
    if result:
        out_path, count = result
        print()
        print("=" * 60)
        print("✨  Готово!")
        print(f"   Файл    : {out_path}")
        print(f"   Товаров : {count}")
        print(f"   Время   : {elapsed:.1f} сек")
        print("=" * 60)


if __name__ == "__main__":
    main()
    input("\nНажми Enter для выхода...")