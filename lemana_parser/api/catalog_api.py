"""Сбор товаров через внутренний API каталога."""

from __future__ import annotations

import logging

from curl_cffi.requests import AsyncSession

from lemana_parser.api.client import LemanaApiClient, LemanaApiError, chunked
from lemana_parser.api.normalizers import normalize_api_product
from lemana_parser.api.state import PlpStateError, build_plp_api_context
from lemana_parser.config import CONFIG
from lemana_parser.http_utils import fetch_with_retry
from lemana_parser.models import Product

logger = logging.getLogger("api.catalog")


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
) -> list[Product]:
    products_data = await client.get_products_data(product_ids, sort_id=sort_id)
    media_map = await client.get_products_media(product_ids)

    products_by_id = {
        str(product_data.get("productId")): normalize_api_product(
            product_data,
            media_map.get(str(product_data.get("productId"))),
        )
        for product_data in products_data
    }
    return [products_by_id[product_id] for product_id in product_ids if product_id in products_by_id]


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

    for product_ids in chunked(clean_ids, CONFIG["api_page_size"]):
        batch = await _load_products_batch(client, product_ids)
        for product in batch:
            char_keys.update(product.get("characteristics") or {})
        products.extend(batch)

    missed = [article for article in clean_ids if article not in {p.get("article") for p in products}]
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

    logger.info("API по артикулам: найдено=%d, не найдено=%d", len(products) - len(missed), len(missed))
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

