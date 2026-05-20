"""
http_utils.py — Асинхронные HTTP-запросы через curl_cffi.

Почему переписан:
- Убраны Cache-Control: no-cache и Pragma: no-cache.
  Для обычной браузерной навигации это лишние и подозрительные заголовки.
- Добавлен нормальный Accept.
- Оставлен ранний выход при 401.
- Оставлен backoff при 403/429.
"""

import asyncio
import logging
import random
from typing import Optional
from urllib.parse import quote, urlparse, urlunparse

from curl_cffi.requests import AsyncSession

from config import CONFIG

logger = logging.getLogger("http_utils")


def _default_headers() -> dict:
    """
    Минимальные заголовки поверх impersonate='chrome124'.

    Важно:
    - НЕ добавляем Cache-Control / Pragma.
    - Cookie берём из CONFIG, если она уже получена.
    """
    headers = {
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    if CONFIG["cookie"]:
        headers["Cookie"] = CONFIG["cookie"]
    return headers


def _encode_url(url: str) -> str:
    """
    Percent-encode кириллицу в query string.
    libcurl требует ASCII URL.
    """
    p = urlparse(url)
    return urlunparse(p._replace(query=quote(p.query, safe="=&+%")))


def create_session() -> AsyncSession:
    """
    AsyncSession с имперсонацией Chrome 124.
    """
    return AsyncSession(
        impersonate="chrome124",
        verify=False,
        timeout=max(CONFIG["catalog_timeout"], CONFIG["product_timeout"]) + 10,
    )


async def fetch_with_retry(
    session: AsyncSession,
    url: str,
    timeout_sec: int,
    tag: str = "URL",
    extra_headers: Optional[dict] = None,
) -> Optional[str]:
    """
    GET с retry.
    Возвращает текст ответа или None.
    """
    safe_url = _encode_url(url)

    for attempt in range(1, CONFIG["max_retries"] + 1):
        try:
            headers = _default_headers()
            if extra_headers:
                headers.update(extra_headers)

            resp = await session.get(
                safe_url,
                headers=headers,
                timeout=timeout_sec,
                allow_redirects=True,
            )

            if resp.status_code == 401:
                logger.error(
                    "[%s] HTTP 401 — cookie отклонена сервером. "
                    "Проверь актуальность cookie и заголовки.",
                    tag,
                )
                return None

            if resp.status_code in (403, 429):
                wait = CONFIG["retry_backoff"] * (attempt ** 2) + random.uniform(0.5, 2.0)
                logger.warning(
                    "[%s] attempt=%d HTTP %d — rate-limit/ban, ждём %.1f сек",
                    tag,
                    attempt,
                    resp.status_code,
                    wait,
                )
                if attempt < CONFIG["max_retries"]:
                    await asyncio.sleep(wait)
                    continue

            if resp.status_code < 400:
                text = resp.text
                if text and len(text) > 200:
                    return text

                logger.warning(
                    "[%s] attempt=%d status=%d short body (%d chars)",
                    tag,
                    attempt,
                    resp.status_code,
                    len(text or ""),
                )
            else:
                logger.warning("[%s] attempt=%d HTTP %d", tag, attempt, resp.status_code)

        except asyncio.TimeoutError:
            logger.warning("[%s] attempt=%d timeout", tag, attempt)
        except Exception as exc:
            logger.warning("[%s] attempt=%d error: %s", tag, attempt, exc)

        if attempt < CONFIG["max_retries"]:
            await asyncio.sleep(CONFIG["retry_backoff"] * (attempt ** 2))

    logger.error("[%s] retry exhausted: %s", tag, url)
    return None


def compute_adaptive_sleep(batch_ms: float) -> float:
    """
    Адаптивная пауза после батча, сек.
    Чем быстрее ответы — тем длиннее пауза.
    """
    lo, hi = CONFIG["min_sleep_ms"], CONFIG["max_sleep_ms"]

    if batch_ms >= 2500:
        return lo / 1000
    if batch_ms <= 800:
        return hi / 1000

    k = (2500 - batch_ms) / (2500 - 800)
    return (lo + k * (hi - lo)) / 1000