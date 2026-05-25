"""
products.py — Параллельная загрузка и парсинг карточек товаров.
"""

import asyncio
import logging
import time
from collections import Counter

from lemana_parser.config import CONFIG
from lemana_parser.http_utils import fetch_with_retry_result
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
            fetch_result = await fetch_with_retry_result(
                session,
                item["url"],
                CONFIG["product_timeout"],
                tag,
                extra_headers={
                    "Referer": CONFIG["catalog_first_page_url"],
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
                stop_on_status_codes={403, 429},
            )
            http_meta = {
                "_http_status": fetch_result.status_code or 0,
                "_http_attempts": fetch_result.attempts,
                "_retryable_hits": fetch_result.retryable_hits,
            }
            html = fetch_result.html
            if not html:
                status = f"http_{fetch_result.status_code}" if fetch_result.status_code else "fetch_failed"
                error = (
                    f"HTTP {fetch_result.status_code} после {fetch_result.attempts} попыток"
                    if fetch_result.status_code
                    else "Не удалось загрузить карточку"
                )
                if fetch_result.error:
                    error = f"{error}; {fetch_result.error}"
                logger.warning("%s: карточка не загружена", tag)
                product = _base_product(item, status=status, error=error)
                product.update(http_meta)
                return product

            product = _parse_product(html, item)
            product.update(http_meta)
            if not product["name"] and not product["price"] and not product["characteristics"]:
                product["status"] = "parse_empty"
                product["error"] = "Карточка загружена, но ключевые поля не найдены"
            return product
        except Exception as exc:
            logger.exception("%s: ошибка обработки карточки", tag)
            return _base_product(item, status="error", error=f"{type(exc).__name__}: {exc}")


def _product_has_pressure(product: Product) -> bool:
    status = product.get("status", "ok")
    return (
        product.get("_retryable_hits", 0) > 0
        or status in {"http_403", "http_408", "http_429", "http_500", "http_502", "http_503", "http_504"}
    )


def _next_throttle_state(
    batch_size: int,
    sleep_sec: float,
    stable_batches: int,
    pressure_count: int,
) -> tuple[int, float, int]:
    if not CONFIG["product_adaptive_throttle"]:
        return CONFIG["product_concurrency"], CONFIG["product_batch_sleep"], stable_batches

    max_sleep = CONFIG["product_max_batch_sleep"]
    base_sleep = CONFIG["product_batch_sleep"]

    if pressure_count:
        next_batch_size = max(1, batch_size // 2)
        next_sleep = min(max_sleep, max(sleep_sec, base_sleep, 0.5) * 1.7)
        if next_batch_size != batch_size or next_sleep > sleep_sec:
            logger.warning(
                "Антибот-сигналы в батче: %d. Замедляемся: batch=%d, sleep=%.1f сек",
                pressure_count,
                next_batch_size,
                next_sleep,
            )
        return next_batch_size, next_sleep, 0

    stable_batches += 1
    if stable_batches < CONFIG["product_recovery_batches"]:
        return batch_size, sleep_sec, stable_batches

    next_batch_size = min(CONFIG["product_concurrency"], batch_size + 1)
    next_sleep = max(base_sleep, sleep_sec * 0.75)
    if next_batch_size != batch_size or next_sleep < sleep_sec:
        logger.info(
            "Стабильные батчи: ускоряемся: batch=%d, sleep=%.1f сек",
            next_batch_size,
            next_sleep,
        )
    return next_batch_size, next_sleep, 0


async def fetch_and_parse_products(
    session,
    catalog_items: list[CatalogItem],
) -> tuple[list[Product], list[str]]:
    sem = asyncio.Semaphore(CONFIG["product_concurrency"])
    products: list[Product] = []
    deferred_items: list[CatalogItem] = []
    all_char_keys: set[str] = set()
    batch_size = CONFIG["product_concurrency"]
    batch_sleep = CONFIG["product_batch_sleep"]
    stable_batches = 0

    from tqdm import tqdm

    def add_final_product(product: Product) -> None:
        for key in product["characteristics"]:
            all_char_keys.add(key)
        products.append(product)

    def is_deferred_candidate(product: Product) -> bool:
        return CONFIG["product_deferred_retry"] and product.get("status") in {"http_403", "http_429"}

    with tqdm(total=len(catalog_items), desc="🔎 Карточки товаров", unit="шт") as pbar:
        start = 0
        while start < len(catalog_items):
            batch = catalog_items[start : start + batch_size]
            batch_started = time.monotonic()

            results = await asyncio.gather(
                *[_fetch_product(session, item, sem) for item in batch], return_exceptions=True
            )

            deferred_in_batch = 0
            for item, result in zip(batch, results, strict=False):
                if isinstance(result, Exception):
                    logger.exception("Необработанная ошибка батча карточек", exc_info=result)
                    add_final_product(
                        _base_product(item, status="error", error=f"{type(result).__name__}: {result}")
                    )
                    continue

                product = result
                if is_deferred_candidate(product):
                    deferred_items.append(item)
                    deferred_in_batch += 1
                    logger.warning(
                        "PROD_%s: откладываем повтор после антибот-ответа %s",
                        item.get("article", item["url"][-20:]),
                        product.get("status"),
                    )
                    continue

                add_final_product(product)

            failed_count = sum(1 for product in products if product.get("status") != "ok")
            if failed_count:
                pbar.set_postfix({"ошибок": failed_count})

            pbar.update(len(batch) - deferred_in_batch)
            start += len(batch)

            pressure_count = sum(
                1 for result in results if isinstance(result, dict) and _product_has_pressure(result)
            )
            batch_size, batch_sleep, stable_batches = _next_throttle_state(
                batch_size=batch_size,
                sleep_sec=batch_sleep,
                stable_batches=stable_batches,
                pressure_count=pressure_count,
            )

            elapsed = time.monotonic() - batch_started
            if start < len(catalog_items) and batch_sleep > 0:
                logger.debug("Пауза после батча: %.1f сек (батч %.1f сек)", batch_sleep, elapsed)
                await asyncio.sleep(batch_sleep)

            if pressure_count and CONFIG["product_pressure_cooldown"] > 0:
                cooldown = CONFIG["product_pressure_cooldown"]
                logger.warning("Пауза после антибот-сигналов: %.1f сек", cooldown)
                await asyncio.sleep(cooldown)

        if deferred_items:
            cooldown = CONFIG["product_pressure_cooldown"]
            if cooldown > 0:
                logger.warning(
                    "Отложенный повтор карточек: %d шт, пауза %.1f сек",
                    len(deferred_items),
                    cooldown,
                )
                await asyncio.sleep(cooldown)

            retry_sem = asyncio.Semaphore(1)
            for item in deferred_items:
                product = await _fetch_product(session, item, retry_sem)
                add_final_product(product)
                failed_count = sum(1 for product in products if product.get("status") != "ok")
                if failed_count:
                    pbar.set_postfix({"ошибок": failed_count})
                pbar.update(1)
                if CONFIG["product_batch_sleep"] > 0:
                    await asyncio.sleep(max(CONFIG["product_batch_sleep"], 1.0))

    char_keys_sorted = sorted(all_char_keys, key=lambda x: x.lower())
    failed_count = sum(1 for product in products if product.get("status") != "ok")
    if failed_count:
        logger.warning(
            "Карточки товаров: %d из %d с ошибками/пустым парсингом", failed_count, len(products)
        )
    return products, char_keys_sorted
