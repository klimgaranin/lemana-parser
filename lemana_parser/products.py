"""
products.py — Параллельная загрузка и парсинг карточек товаров.
"""

import asyncio
import logging
from collections import Counter

from lemana_parser.config import CONFIG
from lemana_parser.http_utils import fetch_with_retry
from lemana_parser.models import CatalogItem, Product, ProductSummary
from lemana_parser.parsers.html import (
    extract_all_characteristics,
    extract_article_from_url,
    extract_main_image,
    match1,
    parse_price_from_html,
    strip_html,
)

logger = logging.getLogger("products")


def summarize_products(products: list[Product]) -> ProductSummary:
    status_counts = Counter((product.get("status") or "ok") for product in products)
    ok_count = status_counts.get("ok", 0)
    total_count = len(products)
    return {
        "total": total_count,
        "ok": ok_count,
        "errors": total_count - ok_count,
        "status_counts": dict(sorted(status_counts.items())),
    }


def _base_product(item: CatalogItem, status: str = "ok", error: str = "") -> Product:
    url = item["url"]
    return {
        "status": status,
        "error": error,
        "article": item.get("article") or extract_article_from_url(url),
        "url": url,
        "name": item.get("name", ""),
        "price": item.get("price", ""),
        "image": item.get("image", ""),
        "characteristics": {},
    }


def _parse_product(html: str, base: CatalogItem) -> Product:
    result = _base_product(base)

    if not result["name"]:
        h1 = match1(html, r"<h1[^>]*>([\s\S]*?)</h1>")
        result["name"] = strip_html(h1).strip()

    if not result["price"]:
        result["price"] = parse_price_from_html(html)

    if not result["image"]:
        result["image"] = extract_main_image(html)

    result["characteristics"] = extract_all_characteristics(html)
    return result


async def _fetch_product(session, item: CatalogItem, sem: asyncio.Semaphore) -> Product:
    async with sem:
        tag = f"PROD_{item.get('article', item['url'][-20:])}"
        try:
            html = await fetch_with_retry(
                session,
                item["url"],
                CONFIG["product_timeout"],
                tag,
                extra_headers={
                    "Referer": CONFIG["catalog_first_page_url"],
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            if not html:
                logger.warning("%s: карточка не загружена", tag)
                return _base_product(
                    item, status="fetch_failed", error="Не удалось загрузить карточку"
                )

            product = _parse_product(html, item)
            if not product["name"] and not product["price"] and not product["characteristics"]:
                product["status"] = "parse_empty"
                product["error"] = "Карточка загружена, но ключевые поля не найдены"
            return product
        except Exception as exc:
            logger.exception("%s: ошибка обработки карточки", tag)
            return _base_product(item, status="error", error=f"{type(exc).__name__}: {exc}")


async def fetch_and_parse_products(
    session,
    catalog_items: list[CatalogItem],
) -> tuple[list[Product], list[str]]:
    sem = asyncio.Semaphore(CONFIG["product_concurrency"])
    products: list[Product] = []
    all_char_keys: set[str] = set()

    # ИЗМЕНЕНО: убрали * 2 — батч = конкурентность, не больше
    batch_size = CONFIG["product_concurrency"]

    from tqdm import tqdm

    with tqdm(total=len(catalog_items), desc="🔎 Карточки товаров", unit="шт") as pbar:
        for start in range(0, len(catalog_items), batch_size):
            batch = catalog_items[start : start + batch_size]

            results = await asyncio.gather(
                *[_fetch_product(session, item, sem) for item in batch], return_exceptions=True
            )

            for result in results:
                if isinstance(result, Exception):
                    logger.exception("Необработанная ошибка батча карточек", exc_info=result)
                    products.append(
                        {
                            "status": "error",
                            "error": f"{type(result).__name__}: {result}",
                            "article": "",
                            "url": "",
                            "name": "",
                            "price": "",
                            "image": "",
                            "characteristics": {},
                        }
                    )
                    continue

                product = result
                for key in product["characteristics"]:
                    all_char_keys.add(key)
                products.append(product)

            failed_count = sum(1 for product in products if product.get("status") != "ok")
            if failed_count:
                pbar.set_postfix({"ошибок": failed_count})

            pbar.update(len(batch))

            if start + batch_size < len(catalog_items) and CONFIG["product_batch_sleep"] > 0:
                await asyncio.sleep(CONFIG["product_batch_sleep"])

    char_keys_sorted = sorted(all_char_keys, key=lambda x: x.lower())
    failed_count = sum(1 for product in products if product.get("status") != "ok")
    if failed_count:
        logger.warning(
            "Карточки товаров: %d из %d с ошибками/пустым парсингом", failed_count, len(products)
        )
    return products, char_keys_sorted
