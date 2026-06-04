"""Экспериментальный транспорт API-запросов через Google Apps Script."""

from __future__ import annotations

import logging
from typing import Any

from curl_cffi.requests import AsyncSession

from lemana_parser.api.metrics import record_api_status
from lemana_parser.api.state import PlpApiContext
from lemana_parser.config import CONFIG

logger = logging.getLogger("api.gas_proxy")


class LemanaGasProxyError(RuntimeError):
    """GAS proxy не выполнил запрос или вернул ошибку."""


def _trim_response_body(body: str, limit: int = 1000) -> str:
    body = " ".join((body or "").split())
    if len(body) <= limit:
        return body
    return body[:limit] + f"... <обрезано {len(body) - limit} символов>"


def _context_payload(context: PlpApiContext) -> dict[str, Any]:
    return {
        "apiBaseUrl": context.api_base_url,
        "apiKey": context.api_key,
        "requestId": context.request_id,
        "regionId": context.region_id,
        "regionName": context.region_name,
        "familyId": context.family_id,
        "searchMethod": context.search_method,
        "facets": context.facets,
    }


def _fallback_region_ids(primary_region_id: str) -> list[str]:
    result: list[str] = []
    seen = {str(primary_region_id)}
    raw_value = str(CONFIG.get("api_fallback_region_ids") or "")
    for chunk in raw_value.replace(";", ",").split(","):
        region_id = chunk.strip()
        if not region_id or region_id in seen:
            continue
        seen.add(region_id)
        result.append(region_id)
    return result


async def _post_gas_proxy(session: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    response = await session.post(
        CONFIG["gas_proxy_url"],
        json=payload,
        headers={"Accept": "application/json"},
        timeout=CONFIG["catalog_timeout"],
        allow_redirects=True,
    )
    body = response.text
    content_type = response.headers.get("content-type", "") if response.headers else ""
    record_api_status("gas-proxy:webapp", response.status_code)
    if response.status_code >= 400:
        raise LemanaGasProxyError(
            f"GAS proxy HTTP {response.status_code}, "
            f"content-type={content_type}, body={_trim_response_body(body)}"
        )

    try:
        data = response.json()
    except Exception as exc:
        raise LemanaGasProxyError(
            f"GAS proxy вернул не JSON: content-type={content_type}, "
            f"body={_trim_response_body(body)}"
        ) from exc

    if not isinstance(data, dict):
        raise LemanaGasProxyError(f"GAS proxy: ожидался JSON object, получен {type(data).__name__}")
    if not data.get("ok"):
        logs = data.get("logs") if isinstance(data.get("logs"), list) else []
        last_log = logs[-1] if logs else {}
        details = data.get("error") or "неизвестная ошибка"
        if last_log:
            details += f"; last_log={_trim_response_body(str(last_log), 700)}"
        raise LemanaGasProxyError(f"GAS proxy error: {details}")

    logs = data.get("logs") if isinstance(data.get("logs"), list) else []
    for item in logs:
        if not isinstance(item, dict):
            continue
        record_api_status(str(item.get("method") or "gas-proxy:inner"), item.get("statusCode"))
        logger.info(
            "GAS proxy: %s status=%s elapsed=%sms body=%s",
            item.get("method"),
            item.get("statusCode"),
            item.get("elapsedMs"),
            item.get("bodyPreview", ""),
        )
    return data


async def fetch_products_batch_via_gas(
    session: AsyncSession,
    context: PlpApiContext,
    product_ids: list[str],
    *,
    articles_mode: str,
) -> tuple[list[dict], dict[str, dict]]:
    """Загружает один batch products-data/media через GAS Web App."""
    if not CONFIG["gas_proxy_url"]:
        raise LemanaGasProxyError("LEMANA_GAS_PROXY_URL не задан")

    payload = {
        "action": "productsBatch",
        "token": CONFIG["gas_proxy_token"],
        "context": _context_payload(context),
        "productIds": [str(product_id) for product_id in product_ids],
        "articlesMode": articles_mode,
        "fallbackRegionIds": _fallback_region_ids(context.region_id),
        "includeMedia": True,
    }
    data = await _post_gas_proxy(session, payload)
    products_data = data.get("productsData") or []
    if not isinstance(products_data, list):
        raise LemanaGasProxyError("GAS proxy: productsData должен быть списком")
    media_map = data.get("mediaMap") or {}
    if not isinstance(media_map, dict):
        media_map = {}
    return (
        [item for item in products_data if isinstance(item, dict)],
        {str(key): value for key, value in media_map.items() if isinstance(value, dict)},
    )


async def fetch_catalog_page_via_gas(
    session: AsyncSession,
    context: PlpApiContext,
    *,
    offset: int,
) -> tuple[list[str], int, list[dict], dict[str, dict]]:
    """Загружает одну страницу каталога через GAS Web App."""
    if not CONFIG["gas_proxy_url"]:
        raise LemanaGasProxyError("LEMANA_GAS_PROXY_URL не задан")

    data = await _post_gas_proxy(
        session,
        {
            "action": "catalogPage",
            "token": CONFIG["gas_proxy_token"],
            "context": _context_payload(context),
            "offset": offset,
            "limit": CONFIG["api_page_size"],
            "fallbackRegionIds": _fallback_region_ids(context.region_id),
            "includeMedia": True,
        },
    )
    product_ids = [str(product_id) for product_id in data.get("productIds") or []]
    total_count = int(data.get("totalCount") or 0)
    products_data = data.get("productsData") or []
    if not isinstance(products_data, list):
        raise LemanaGasProxyError("GAS proxy: productsData должен быть списком")
    media_map = data.get("mediaMap") or {}
    if not isinstance(media_map, dict):
        media_map = {}
    return (
        product_ids,
        total_count,
        [item for item in products_data if isinstance(item, dict)],
        {str(key): value for key, value in media_map.items() if isinstance(value, dict)},
    )
