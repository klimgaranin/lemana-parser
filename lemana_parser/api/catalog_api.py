"""Сбор товаров через внутренний API каталога."""

from __future__ import annotations

import asyncio
import logging

from curl_cffi.requests import AsyncSession

from lemana_parser.api.client import LemanaApiClient, LemanaApiError, chunked
from lemana_parser.api.gas_proxy import (
    LemanaGasProxyError,
    fetch_catalog_page_via_gas,
    fetch_products_batch_via_gas,
)
from lemana_parser.api.normalizers import normalize_api_product
from lemana_parser.api.state import PlpApiContext, PlpStateError, build_plp_api_context
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
    relaxed_missing_retry: bool = False,
    articles_mode: str = "strict-then-relaxed",
) -> list[Product]:
    if relaxed_missing_retry and articles_mode == "relaxed":
        products_data = await client.get_products_data(
            product_ids,
            include_facets=False,
            filter_by_eligibility=False,
        )
    else:
        products_data = await client.get_products_data(product_ids, sort_id=sort_id)
    products_data_by_id = {str(item.get("productId")): item for item in products_data}

    if relaxed_missing_retry:
        missing_ids = [
            product_id for product_id in product_ids if product_id not in products_data_by_id
        ]
        if missing_ids and articles_mode == "strict-then-relaxed":
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
            request_mode_label = (
                "relaxed-запроса"
                if articles_mode == "relaxed"
                else "relaxed retry"
            )
            logger.info(
                "API по артикулам: %d товаров не вернулись после %s, "
                "оставляем api_data_missing",
                len(missing_ids),
                request_mode_label,
            )

    try:
        media_map = await client.get_products_media(product_ids)
    except LemanaApiError as exc:
        logger.warning("API медиа не загрузились, продолжаем без них: %s", exc)
        media_map = {}

    return _normalize_products_batch(product_ids, list(products_data_by_id.values()), media_map)


def _normalize_products_batch(
    product_ids: list[str],
    products_data: list[dict],
    media_map: dict[str, dict],
) -> list[Product]:
    products_data_by_id = {
        str(product_data.get("productId")): product_data
        for product_data in products_data
        if product_data.get("productId")
    }

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


async def _load_products_batch_gas_proxy(
    session: AsyncSession,
    context: PlpApiContext,
    product_ids: list[str],
) -> list[Product]:
    products_data, media_map = await fetch_products_batch_via_gas(
        session,
        context,
        product_ids,
        articles_mode=CONFIG["api_articles_mode"],
    )
    return _normalize_products_batch(product_ids, products_data, media_map)


async def _load_catalog_page_gas_proxy(
    session: AsyncSession,
    context: PlpApiContext,
    *,
    offset: int,
) -> tuple[list[str], int, list[Product]]:
    product_ids, total_count, products_data, media_map = await fetch_catalog_page_via_gas(
        session,
        context,
        offset=offset,
    )
    return (
        product_ids,
        total_count,
        _normalize_products_batch(product_ids, products_data, media_map),
    )


async def _load_catalog_page(
    session: AsyncSession,
    context: PlpApiContext,
    client: LemanaApiClient,
    *,
    offset: int,
) -> tuple[int, list[str], int, list[Product]]:
    if CONFIG["api_transport"] in {"gas", "gas-fallback"}:
        try:
            logger.info(
                "API каталог: offset=%d через GAS proxy (batch=%d)",
                offset,
                CONFIG["api_page_size"],
            )
            product_ids, api_total, batch_products = await _load_catalog_page_gas_proxy(
                session,
                context,
                offset=offset,
            )
            return offset, product_ids, api_total, batch_products
        except LemanaGasProxyError as exc:
            if CONFIG["api_transport"] == "gas":
                raise LemanaApiError(f"GAS proxy catalog offset={offset}: {exc}") from exc
            logger.warning(
                "GAS proxy не сработал для каталога offset=%d: %s. "
                "Добираем страницу локальным API.",
                offset,
                exc,
            )

    product_ids, api_total = await client.search_product_ids(offset=offset)
    batch_products = await _load_products_batch(client, product_ids)
    return offset, product_ids, api_total, batch_products


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

    batches = list(chunked(clean_ids, CONFIG["api_page_size"]))
    for batch_index, product_ids in enumerate(batches, start=1):
        if CONFIG["api_transport"] in {"gas", "gas-fallback"}:
            try:
                logger.info(
                    "API по артикулам: batch %d/%d через GAS proxy (%d шт)",
                    batch_index,
                    len(batches),
                    len(product_ids),
                )
                batch = await _load_products_batch_gas_proxy(session, context, product_ids)
            except LemanaGasProxyError as exc:
                if CONFIG["api_transport"] == "gas":
                    raise LemanaApiError(f"GAS proxy batch {batch_index}/{len(batches)}: {exc}") from exc
                logger.warning(
                    "GAS proxy не сработал для batch %d/%d: %s. "
                    "Добираем batch локальным API.",
                    batch_index,
                    len(batches),
                    exc,
                )
                batch = await _load_products_batch(
                    client,
                    product_ids,
                    relaxed_missing_retry=True,
                    articles_mode=CONFIG["api_articles_mode"],
                )
        else:
            batch = await _load_products_batch(
                client,
                product_ids,
                relaxed_missing_retry=True,
                articles_mode=CONFIG["api_articles_mode"],
            )
        for product in batch:
            char_keys.update(product.get("characteristics") or {})
        products.extend(batch)
        if CONFIG["api_articles_sleep"] > 0 and batch_index < len(batches):
            logger.info(
                "API по артикулам: пауза %.1f сек после batch %d/%d",
                CONFIG["api_articles_sleep"],
                batch_index,
                len(batches),
            )
            await asyncio.sleep(CONFIG["api_articles_sleep"])

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
    char_keys: set[str] = set()
    total_count = context.total_count or CONFIG["max_products"]
    progress_total = min(total_count, CONFIG["max_products"])
    offsets = list(range(0, progress_total, CONFIG["api_page_size"]))
    if not offsets:
        raise LemanaApiError("API каталога вернул 0 товаров")
    concurrency = min(CONFIG["api_catalog_concurrency"], len(offsets))
    if concurrency > 1:
        logger.info(
            "API каталог: параллельная загрузка offset страниц, concurrency=%d",
            concurrency,
        )

    from tqdm import tqdm

    page_results: list[tuple[int, list[str], int, list[Product]]] = []
    loaded_char_keys: set[str] = set()

    semaphore = asyncio.Semaphore(concurrency)

    async def load_offset(offset: int) -> tuple[int, list[str], int, list[Product]]:
        async with semaphore:
            return await _load_catalog_page(session, context, client, offset=offset)

    with tqdm(total=progress_total, desc="API каталог", unit="шт") as pbar:
        tasks = [asyncio.create_task(load_offset(offset)) for offset in offsets]
        try:
            for task in asyncio.as_completed(tasks):
                offset, page_product_ids, api_total, batch_products = await task
                page_results.append((offset, page_product_ids, api_total, batch_products))
                if api_total:
                    total_count = min(api_total, CONFIG["max_products"])
                    if pbar.total != total_count:
                        pbar.total = total_count
                        pbar.refresh()
                for product in batch_products:
                    loaded_char_keys.update(product.get("characteristics") or {})
                pbar.update(min(len(batch_products), max(0, progress_total - offset)))
                pbar.set_postfix({"offset": offset, "chars": len(loaded_char_keys)})
        except Exception:
            for task in tasks:
                task.cancel()
            raise

    products: list[Product] = []
    for _offset, _product_ids, _api_total, batch_products in sorted(
        page_results,
        key=lambda item: item[0],
    ):
        limit_left = CONFIG["max_products"] - len(products)
        if limit_left <= 0:
            break
        for product in batch_products[:limit_left]:
            char_keys.update(product.get("characteristics") or {})
        products.extend(batch_products[:limit_left])

    if not products:
        raise LemanaApiError("API каталога вернул 0 товаров")

    logger.info("API каталог: собрано %d товаров", len(products))
    return products, sorted(char_keys)
