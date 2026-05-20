"""
products.py — Параллельная загрузка и парсинг карточек товаров.
"""
import asyncio
import logging
import time
from typing import List, Dict, Tuple

from config import CONFIG
from http_utils import fetch_with_retry, compute_adaptive_sleep
from utils import (
    strip_html, match1, extract_article_from_url,
    parse_price_from_html, extract_main_image,
    extract_all_characteristics,
)

logger = logging.getLogger("products")


def _parse_product(html: str, base: Dict) -> Dict:
    result = {
        "article": base.get("article") or extract_article_from_url(base["url"]),
        "url":     base["url"],
        "name":    base.get("name", ""),
        "price":   base.get("price", ""),
        "image":   base.get("image", ""),
        "characteristics": {},
    }

    if not result["name"]:
        h1 = match1(html, r"<h1[^>]*>([\s\S]*?)</h1>")
        result["name"] = strip_html(h1).strip()

    if not result["price"]:
        result["price"] = parse_price_from_html(html)

    if not result["image"]:
        result["image"] = extract_main_image(html)

    result["characteristics"] = extract_all_characteristics(html)
    return result


async def _fetch_product(session, item: Dict, sem: asyncio.Semaphore) -> Dict:
    async with sem:
        tag = f"PROD_{item.get('article', item['url'][-20:])}"
        html = await fetch_with_retry(
            session,
            item["url"],
            CONFIG["product_timeout"],
            tag, 
            extra_headers={
                "Referer": CONFIG["catalog_first_page_url"],   # ← имитируем переход с каталога
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        if not html:
            return {
                "article": item.get("article", ""),
                "url":     item["url"],
                "name":    item.get("name", ""),
                "price":   item.get("price", ""),
                "image":   item.get("image", ""),
                "characteristics": {},
            }
        return _parse_product(html, item)


async def fetch_and_parse_products(
    session,
    catalog_items: List[Dict],
) -> Tuple[List[Dict], List[str]]:
    sem = asyncio.Semaphore(CONFIG["product_concurrency"])
    products: List[Dict] = []
    all_char_keys: Dict[str, bool] = {}

    # ИЗМЕНЕНО: убрали * 2 — батч = конкурентность, не больше
    batch_size = CONFIG["product_concurrency"]

    from tqdm import tqdm
    with tqdm(total=len(catalog_items), desc="🔎 Карточки товаров", unit="шт") as pbar:

        for start in range(0, len(catalog_items), batch_size):
            batch = catalog_items[start: start + batch_size]

            results = await asyncio.gather(*[
                _fetch_product(session, item, sem) for item in batch
            ])

            for product in results:
                for key in product["characteristics"]:
                    all_char_keys[key] = True
                products.append(product)

            pbar.update(len(batch))

            # ИЗМЕНЕНО: фиксированная пауза 4 сек между батчами (вместо адаптивной)
            # Даём серверу "остыть" после каждой волны запросов
            if start + batch_size < len(catalog_items):
                await asyncio.sleep(4.0)

    char_keys_sorted = sorted(all_char_keys.keys(), key=lambda x: x.lower())
    return products, char_keys_sorted
