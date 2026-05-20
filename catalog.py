"""
catalog.py — Сбор товаров из HTML-страниц каталога LemanapPRO.

Что исправлено:
1. Убран жёсткий срез products-list на 250_000 символов.
2. Пагинация больше НЕ зависит от __NEXT_DATA__, потому что на реальном ответе
   его может не быть.
3. totalPages берём из HTML-пагинации и/или считаем по totalCount / items_on_page1.
4. Если totalPages оценён неверно, добираем следующие страницы до двух пустых подряд.
5. Подробное логирование по каждой странице.
"""

import asyncio
import logging
import math
import re
import time
from typing import Dict, List, Set
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from config import CONFIG
from http_utils import fetch_with_retry, compute_adaptive_sleep
from utils import (
    strip_html,
    decode_html,
    remove_spaces,
    match1,
    extract_article_from_url,
    extract_base_url,
    normalize_url,
    format_fixed,
    _extract_price_integer_primary,
)

logger = logging.getLogger("catalog")


# ─────────────────────────────────────────────────────────────────────────────
# URL helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_page_url(page: int) -> str:
    """
    Аккуратно выставляет/заменяет query-параметр page.
    Так мы не плодим ?page=2&page=3&page=4.
    """
    base = CONFIG["catalog_first_page_url"]
    if page <= 1:
        return base

    parts = urlsplit(base)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["page"] = str(page)
    new_query = urlencode(query, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


# ─────────────────────────────────────────────────────────────────────────────
# Пагинация и счётчики
# ─────────────────────────────────────────────────────────────────────────────

def _parse_products_count(html: str) -> int:
    """
    Пытаемся вытащить totalCount из HTML.
    """
    if not html:
        return 0

    patterns = [
        r'data-qa-products-count=["\'](\d+)["\']',
        r'data-qa=["\']products-count["\'][^>]*>\s*(\d+)\s*<',
        r'(\d+)\s*товар(?:ов|а)?',
    ]
    for pattern in patterns:
        m = re.search(pattern, html, re.I)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
    return 0


def _parse_last_page_from_html(html: str) -> int:
    """
    Ищем максимальный page=N в ссылках пагинации.
    """
    if not html:
        return 0

    pages = [int(x) for x in re.findall(r'[?&]page=(\d+)', html, re.I)]
    return max(pages) if pages else 0


# ─────────────────────────────────────────────────────────────────────────────
# Выделение зоны товаров
# ─────────────────────────────────────────────────────────────────────────────

def _extract_products_list_scope(html: str) -> str:
    """
    Убираем старый баг со срезом на 250_000 символов.

    Логика:
    - ищем начало блока products-list;
    - ищем ближайший конец: pagination / catalog-bottom / footer;
    - если блок не найден, работаем по всему HTML.
    """
    if not html:
        return ""

    start_m = re.search(r'data-qa=["\']products-list["\']', html, re.I)
    if not start_m:
        start_m = re.search(r'data-qa=["\'](?:catalog-products|product-list)["\']', html, re.I)

    if not start_m:
        logger.warning("products-list не найден — парсим весь HTML")
        return html

    start = start_m.start()
    tail = html[start_m.end():]

    end_markers = [
        r'data-qa=["\']pagination["\']',
        r'data-qa=["\']catalog-bottom["\']',
        r'<footer[\s>]',
    ]

    end = len(html)
    for marker in end_markers:
        em = re.search(marker, tail, re.I)
        if em:
            candidate = start_m.end() + em.start()
            if candidate < end:
                end = candidate

    scope = html[start:end]
    logger.debug("products-list scope: %d chars (из %d total)", len(scope), len(html))
    return scope


# ─────────────────────────────────────────────────────────────────────────────
# Парсинг карточек
# ─────────────────────────────────────────────────────────────────────────────

def _extract_catalog_items(html: str, base_url: str) -> List[Dict]:
    """
    Извлекает карточки товаров из HTML одной страницы.
    """
    out: List[Dict] = []
    seen_urls: Set[str] = set()

    scope = _extract_products_list_scope(html) or (html or "")

    starts = [
        (m.start(), m.group(1))
        for m in re.finditer(
            r'<div[^>]+data-qa=["\']product["\'][^>]*data-product-id=["\']([^"\']+)["\']',
            scope,
            re.I,
        )
    ]

    if not starts:
        starts = [
            (m.start(), m.group(1))
            for m in re.finditer(
                r'<div[^>]+data-product-id=["\']([^"\']+)["\']',
                scope,
                re.I,
            )
        ]

    if not starts:
        logger.warning("Карточки не найдены в scope (%d chars)", len(scope))
        return out

    logger.debug("Найдено стартов карточек: %d", len(starts))

    for i, (start_idx, prod_id) in enumerate(starts):
        end_idx = starts[i + 1][0] if i + 1 < len(starts) else len(scope)
        block = scope[start_idx:end_idx]

        href = (
            match1(block, r'<a[^>]+href=["\'](/catalogue/[^"\']+)["\']')
            or match1(block, r'<a[^>]+href=["\'](/[^"\']+)["\']')
            or match1(block, r'href=["\'](/[^"\']+)["\']')
        )
        if not href:
            continue

        url = normalize_url(href, base_url)
        if url in seen_urls:
            continue
        seen_urls.add(url)

        name = (
            strip_html(match1(block, r'data-qa=["\']product-name["\'][^>]*>(.*?)</'))
            or strip_html(match1(block, r'itemprop=["\']name["\'][^>]*>(.*?)</'))
            or decode_html(match1(block, r'aria-label=["\']([^"\']+)["\']'))
            or ""
        ).strip()

        img = (
            match1(block, r'img[^>]+itemprop=["\']image["\'][^>]+src=["\']([^"\']+)["\']')
            or match1(block, r'img[^>]+src=["\']([^"\']+)["\']')
            or ""
        ).strip()

        price_raw = _extract_price_integer_primary(block)
        if not price_raw:
            pm = re.search(
                r'data-testid=["\']price-integer["\'][^>]*><span[^>]*>([^<]+)</span>',
                block,
                re.I,
            )
            if pm:
                price_raw = remove_spaces(decode_html(strip_html(pm.group(1))))

        price = format_fixed(price_raw, 2)

        out.append(
            {
                "article": prod_id or extract_article_from_url(url),
                "url": url,
                "name": name,
                "price": price,
                "image": img,
            }
        )

    return out


# ─────────────────────────────────────────────────────────────────────────────
# Сетевые вызовы
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_page(session, page: int, base_url: str, sem: asyncio.Semaphore) -> List[Dict]:
    async with sem:
        url = _build_page_url(page)
        html = await fetch_with_retry(
            session,
            url,
            CONFIG["catalog_timeout"],
            tag=f"CATALOG p={page}",
            extra_headers={"Referer": _build_page_url(max(1, page - 1))},
        )
        if not html:
            logger.warning("page=%d: пустой ответ", page)
            return []

        items = _extract_catalog_items(html, base_url)
        logger.info("page=%d → %d товаров", page, len(items))
        return items


# ─────────────────────────────────────────────────────────────────────────────
# Основной сбор
# ─────────────────────────────────────────────────────────────────────────────

async def collect_catalog_items(session) -> List[Dict]:
    """
    Собирает все товары каталога.
    Возвращает список уникальных товаров.
    """
    base_url = extract_base_url(CONFIG["catalog_first_page_url"])
    items_map: Dict[str, Dict] = {}

    # ── page 1 ───────────────────────────────────────────────────────────────
    html1 = await fetch_with_retry(
        session,
        _build_page_url(1),
        CONFIG["catalog_timeout"],
        tag="CATALOG p=1",
    )
    if not html1:
        raise RuntimeError(
            "Страница 1 недоступна. Проверь URL, cookie и http_utils.py"
        )

    items1 = _extract_catalog_items(html1, base_url)
    if not items1:
        raise RuntimeError(
            f"Страница 1 вернула 0 товаров (HTML={len(html1)} chars). "
            f"Скорее всего сайт отдал shell/заглушку или изменилась разметка."
        )

    for it in items1:
        items_map[it["url"]] = it

    total_count = _parse_products_count(html1)
    items_on_first_page = len(items1)
    last_page_from_html = _parse_last_page_from_html(html1)

    computed_pages = 0
    if total_count and items_on_first_page:
        computed_pages = math.ceil(total_count / items_on_first_page)

    total_pages = max(last_page_from_html, computed_pages, 1)

    logger.info(
        "page=1 → %d товаров | totalCount=%d | htmlPages=%d | computedPages=%d | chosenPages=%d",
        items_on_first_page,
        total_count,
        last_page_from_html,
        computed_pages,
        total_pages,
    )

    # ── pages 2..N ──────────────────────────────────────────────────────────
    sem = asyncio.Semaphore(CONFIG["catalog_concurrency"])

    try:
        from tqdm import tqdm
        pbar = tqdm(total=max(total_pages - 1, 0), desc="Каталог", unit="стр")
    except Exception:
        pbar = None

    async def fetch_batch(page_numbers: List[int]) -> None:
        t0 = time.monotonic()

        results = await asyncio.gather(
            *[_fetch_page(session, p, base_url, sem) for p in page_numbers]
        )

        for page_items in results:
            for it in page_items:
                if it["url"] not in items_map:
                    items_map[it["url"]] = it

        if pbar:
            pbar.update(len(page_numbers))
            pbar.set_postfix({"товаров": len(items_map)})

        elapsed_ms = (time.monotonic() - t0) * 1000 / max(len(page_numbers), 1)
        sleep_sec = compute_adaptive_sleep(elapsed_ms)
        if sleep_sec > 0:
            await asyncio.sleep(sleep_sec)

    if total_pages >= 2:
        pages = list(range(2, total_pages + 1))
        batch_size = max(1, CONFIG["catalog_concurrency"] * 2)

        for start in range(0, len(pages), batch_size):
            batch = pages[start:start + batch_size]
            await fetch_batch(batch)

            if len(items_map) >= CONFIG["max_products"]:
                logger.info("Достигнут max_products=%d", CONFIG["max_products"])
                result = list(items_map.values())[:CONFIG["max_products"]]
                if pbar:
                    pbar.close()
                return result

    # ── добор, если total_pages был занижен ─────────────────────────────────
    next_page = total_pages + 1
    empty_streak = 0

    while next_page <= CONFIG["max_pages_safety"]:
        if total_count and len(items_map) >= total_count:
            break

        page_items = await _fetch_page(session, next_page, base_url, sem)

        if not page_items:
            empty_streak += 1
            logger.info("page=%d → пусто (empty_streak=%d)", next_page, empty_streak)
        else:
            empty_streak = 0
            for it in page_items:
                if it["url"] not in items_map:
                    items_map[it["url"]] = it

        if empty_streak >= 2:
            break

        next_page += 1

    if pbar:
        pbar.close()

    result = list(items_map.values())[:CONFIG["max_products"]]
    logger.info(
        "Итого собрано: %d товаров%s",
        len(result),
        f" (ожидалось ~{total_count})" if total_count else "",
    )
    return result