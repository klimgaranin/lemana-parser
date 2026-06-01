"""Сбор товаров через внутренний API каталога."""

from __future__ import annotations

import asyncio
import logging

from curl_cffi.requests import AsyncSession

from lemana_parser.api.client import LemanaApiClient, LemanaApiError, chunked
from lemana_parser.api.normalizers import normalize_api_product
from lemana_parser.api.state import PlpStateError, build_plp_api_context
from lemana_parser.config import CONFIG
from lemana_parser.http_utils import fetch_with_retry
from lemana_parser.models import Product

logger = logging.getLogger("api.catalog")


def _api_failed_products(product_ids: list[str], exc: LemanaApiError) -> list[Product]:
    return [
        {
            "status": "api_request_failed",
            "error": str(exc),
            "article": product_id,
            "url": "",
            "name": "",
            "price": "",
            "image": "",
            "characteristics": {},
        }
        for product_id in product_ids
    ]


async def load_api_context(session: AsyncSession):
    html = await fetch_with_retry(
        session,
        CONFIG["catalog_first_page_url"],
        CONFIG["catalog_timeout"],
        tag="API INIT",
        extra_headers={"Referer": "https://lemanapro.ru/"},
    )
    if not html:
        raise LemanaApiError("не удалось загрузить первую страницу каталога для API-контекста")
    try:
        return build_plp_api_context(html, CONFIG["catalog_first_page_url"])
    except PlpStateError as exc:
        raise LemanaApiError(f"не удалось разобрать API-контекст каталога: {exc}") from exc


async def _load_products_batch(
    client: LemanaApiClient,
    product_ids: list[str],
    *,
    sort_id: str | None = None,
    relaxed_missing_retry: bool = False,
) -> list[Product]:
    products_data = await client.get_products_data(product_ids, sort_id=sort_id)
    products_data_by_id = {str(item.get("productId")): item for item in products_data}

    if relaxed_missing_retry:
        missing_ids = [
            product_id for product_id in product_ids if product_id not in products_data_by_id
        ]
        if missing_ids:
            logger.info(
                "API по артикулам: %d товаров не вернулись в строгом запросе, "
                "повторяем без фасетов и eligibility",
                len(missing_ids),
            )
            relaxed_data = await client.get_products_data(
                missing_ids,
                include_facets=False,
                filter_by_eligibility=False,
            )
            products_data_by_id.update(
                {str(item.get("productId")): item for item in relaxed_data if item.get("productId")}
            )

        missing_ids = [
            product_id for product_id in product_ids if product_id not in products_data_by_id
        ]
        if missing_ids:
            logger.info(
                "API по артикулам: %d товаров всё ещё без данных, повторяем без regionId",
                len(missing_ids),
            )
            try:
                global_data = await client.get_products_data(
                    missing_ids,
                    include_facets=False,
                    filter_by_eligibility=False,
                    include_region=False,
                )
            except LemanaApiError as exc:
                logger.warning("API без regionId не сработал: %s", exc)
            else:
                products_data_by_id.update(
                    {
                        str(item.get("productId")): item
                        for item in global_data
                        if item.get("productId")
                    }
                )

    try:
        media_map = await client.get_products_media(product_ids)
    except LemanaApiError as exc:
        logger.warning("API медиа не загрузились, продолжаем без них: %s", exc)
        media_map = {}

    products_by_id = {
        str(product_data.get("productId")): normalize_api_product(
            product_data,
            media_map.get(str(product_data.get("productId"))),
        )
        for product_data in products_data_by_id.values()
    }
    result: list[Product] = []
    for product_id in product_ids:
        product = products_by_id.get(product_id)
        if product:
            result.append(product)
        else:
            result.append(
                {
                    "status": "api_data_missing",
                    "error": "API вернул артикул в поиске, но не вернул данные товара",
                    "article": product_id,
                    "url": "",
                    "name": "",
                    "price": "",
                    "image": "",
                    "characteristics": {},
                }
            )
    return result


async def _load_articles_batch_resilient(
    client: LemanaApiClient,
    product_ids: list[str],
    *,
    depth: int = 0,
) -> list[Product]:
    try:
        return await _load_products_batch(client, product_ids, relaxed_missing_retry=True)
    except LemanaApiError as exc:
        if exc.is_pressure_status and len(product_ids) > 1:
            mid = len(product_ids) // 2
            left = product_ids[:mid]
            right = product_ids[mid:]
            logger.warning(
                "API по артикулам: batch=%d получил %s, делим на %d + %d",
                len(product_ids),
                exc,
                len(left),
                len(right),
            )
            await asyncio.sleep(CONFIG["api_antibot_cooldown"])
            left_products = await _load_articles_batch_resilient(
                client, left, depth=depth + 1
            )
            if CONFIG["api_request_sleep"]:
                await asyncio.sleep(CONFIG["api_request_sleep"])
            right_products = await _load_articles_batch_resilient(
                client, right, depth=depth + 1
            )
            return left_products + right_products

        logger.warning(
            "API по артикулам: batch=%d не загрузился, строки будут в Excel со статусом ошибки: %s",
            len(product_ids),
            exc,
        )
        return _api_failed_products(product_ids, exc)


async def fetch_products_by_articles_api(
    session: AsyncSession,
    article_ids: list[str],
) -> tuple[list[Product], list[str]]:
    context = await load_api_context(session)
    client = LemanaApiClient(session, context)
    products: list[Product] = []
    char_keys: set[str] = set()

    clean_ids = []
    seen = set()
    for article in article_ids:
        article = str(article).strip()
        if article and article not in seen:
            seen.add(article)
            clean_ids.append(article)

    from tqdm import tqdm

    batch_size = CONFIG["api_article_batch_size"]
    with tqdm(total=len(clean_ids), desc="API артикулы", unit="шт") as pbar:
        for product_ids in chunked(clean_ids, batch_size):
            batch = await _load_articles_batch_resilient(client, product_ids)
            for product in batch:
                char_keys.update(product.get("characteristics") or {})
            products.extend(batch)
            pbar.update(len(batch))
            pbar.set_postfix(
                {
                    "batch": len(product_ids),
                    "ok": sum(1 for product in products if product.get("status") == "ok"),
                    "err": sum(1 for product in products if product.get("status") != "ok"),
                }
            )
            if CONFIG["api_request_sleep"] and len(products) < len(clean_ids):
                await asyncio.sleep(CONFIG["api_request_sleep"])

    missed = [
        article for article in clean_ids if article not in {p.get("article") for p in products}
    ]
    for article in missed:
        products.append(
            {
                "status": "api_not_found",
                "error": "API не вернул товар по артикулу ЛМ",
                "article": article,
                "url": "",
                "name": "",
                "price": "",
                "image": "",
                "characteristics": {},
            }
        )

    ok_count = sum(1 for product in products if product.get("status") == "ok")
    error_count = len(products) - ok_count
    logger.info("API по артикулам: успешно=%d, ошибок=%d", ok_count, error_count)
    return products, sorted(char_keys)


async def fetch_catalog_products_api(session: AsyncSession) -> tuple[list[Product], list[str]]:
    context = await load_api_context(session)
    client = LemanaApiClient(session, context)
    products: list[Product] = []
    char_keys: set[str] = set()
    total_count = context.total_count or CONFIG["max_products"]
    offset = 0

    from tqdm import tqdm

    progress_total = min(total_count, CONFIG["max_products"])
    with tqdm(total=progress_total, desc="API каталог", unit="шт") as pbar:
        while len(products) < CONFIG["max_products"] and offset < total_count:
            product_ids, api_total = await client.search_product_ids(offset=offset)
            if api_total:
                total_count = min(api_total, CONFIG["max_products"])
                if pbar.total != total_count:
                    pbar.total = total_count
                    pbar.refresh()
            if not product_ids:
                break

            limit_left = CONFIG["max_products"] - len(products)
            product_ids = product_ids[:limit_left]
            batch_products = await _load_products_batch(client, product_ids)
            for product in batch_products:
                char_keys.update(product.get("characteristics") or {})
            products.extend(batch_products)
            pbar.update(len(batch_products))
            pbar.set_postfix({"offset": offset, "chars": len(char_keys)})

            offset += CONFIG["api_page_size"]

            if len(product_ids) < CONFIG["api_page_size"]:
                break

    if not products:
        raise LemanaApiError("API каталога вернул 0 товаров")

    logger.info("API каталог: собрано %d товаров", len(products))
    return products, sorted(char_keys)
