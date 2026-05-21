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
from typing import Mapping
from urllib.parse import quote, urlparse, urlunparse

from curl_cffi.requests import AsyncSession

from lemana_parser.config import CONFIG

logger = logging.getLogger("http_utils")

MIN_HTML_CHARS = 200
RETRYABLE_STATUS_CODES = {403, 408, 429, 500, 502, 503, 504}


def describe_cookie(cookie: str) -> str:
    if not cookie:
        return "нет"
    return f"{len(cookie)} симв, qrator_jsid2={'да' if 'qrator_jsid2' in cookie else 'нет'}"


def build_headers(
    cookie: str | None = None,
    extra_headers: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """
    Минимальные заголовки поверх impersonate='chrome124'.

    Важно:
    - НЕ добавляем Cache-Control / Pragma.
    - Cookie берём из аргумента или CONFIG, если она уже получена.
    """
    headers = {
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    cookie_value = CONFIG["cookie"] if cookie is None else cookie
    if cookie_value:
        headers["Cookie"] = cookie_value
    if extra_headers:
        headers.update(extra_headers)
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


def _retry_delay(attempt: int, status_code: int | None = None) -> float:
    base = CONFIG["retry_backoff"] * (attempt ** 2)
    jitter = random.uniform(0.5, 2.0) if status_code in {403, 429} else random.uniform(0.1, 0.7)
    return base + jitter


def _response_meta(resp) -> str:
    content_type = resp.headers.get("content-type", "") if getattr(resp, "headers", None) else ""
    final_url = getattr(resp, "url", "") or ""
    return f"status={resp.status_code}, url={final_url}, content-type={content_type}"


async def fetch_with_retry(
    session: AsyncSession,
    url: str,
    timeout_sec: int,
    tag: str = "URL",
    extra_headers: Mapping[str, str] | None = None,
) -> str | None:
    """
    GET с retry.
    Возвращает текст ответа или None.
    """
    safe_url = _encode_url(url)
    logger.debug("[%s] GET %s | cookie: %s", tag, safe_url, describe_cookie(CONFIG["cookie"]))

    for attempt in range(1, CONFIG["max_retries"] + 1):
        try:
            resp = await session.get(
                safe_url,
                headers=build_headers(extra_headers=extra_headers),
                timeout=timeout_sec,
                allow_redirects=True,
            )

            if resp.status_code == 401:
                logger.error(
                    "[%s] HTTP 401 — cookie отклонена сервером (%s). "
                    "Обнови LEMANA_COOKIE через get_cookie.bat или вручную.",
                    tag,
                    describe_cookie(CONFIG["cookie"]),
                )
                return None

            if resp.status_code in RETRYABLE_STATUS_CODES:
                wait = _retry_delay(attempt, resp.status_code)
                logger.warning(
                    "[%s] attempt=%d %s — retry через %.1f сек",
                    tag,
                    attempt,
                    _response_meta(resp),
                    wait,
                )
                if attempt < CONFIG["max_retries"]:
                    await asyncio.sleep(wait)
                    continue

            if resp.status_code < 400:
                text = resp.text
                if text and len(text) >= MIN_HTML_CHARS:
                    return text

                logger.warning(
                    "[%s] attempt=%d status=%d short body (%d chars)",
                    tag,
                    attempt,
                    resp.status_code,
                    len(text or ""),
                )
            else:
                logger.warning("[%s] attempt=%d %s", tag, attempt, _response_meta(resp))

        except TimeoutError:
            logger.warning("[%s] attempt=%d timeout", tag, attempt)
        except Exception as exc:
            logger.warning("[%s] attempt=%d error: %s: %s", tag, attempt, type(exc).__name__, exc)

        if attempt < CONFIG["max_retries"]:
            wait = _retry_delay(attempt)
            logger.debug("[%s] attempt=%d retry через %.1f сек", tag, attempt, wait)
            await asyncio.sleep(wait)

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
