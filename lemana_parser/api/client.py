"""Тонкий клиент внутренних API каталога lemanapro.ru."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Iterable

from curl_cffi.requests import AsyncSession

from lemana_parser.api.debug_log import log_api_request, log_api_response
from lemana_parser.api.state import PlpApiContext
from lemana_parser.config import CONFIG

logger = logging.getLogger("api.client")


class LemanaApiError(RuntimeError):
    """API lemanapro.ru вернул ошибку или неожиданный ответ."""

    def __init__(
        self,
        message: str,
        *,
        method: str | None = None,
        status_code: int | None = None,
        qrator_blocked: bool = False,
        support_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.method = method
        self.status_code = status_code
        self.qrator_blocked = qrator_blocked
        self.support_id = support_id

    @property
    def is_pressure_status(self) -> bool:
        return self.qrator_blocked or self.status_code in {403, 429} or (
            self.status_code is not None and self.status_code >= 500
        )


def chunked(items: list[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _response_text(response) -> str:
    text = getattr(response, "text", "")
    if callable(text):
        try:
            text = text()
        except Exception:
            text = ""
    if isinstance(text, bytes):
        return text.decode("utf-8", errors="replace")
    return str(text or "")


def _is_qrator_access_blocked(response) -> bool:
    headers = getattr(response, "headers", {}) or {}
    server = str(headers.get("server") or headers.get("Server") or "").lower()
    content_type = str(
        headers.get("content-type") or headers.get("Content-Type") or ""
    ).lower()
    body = _response_text(response).lower()
    return (
        getattr(response, "status_code", None) == 403
        and "qrator" in server
        and "text/html" in content_type
        and "access to resource was blocked" in body
    )


def _extract_qrator_support_id(response) -> str | None:
    body = _response_text(response)
    match = re.search(r"Reason or support ID:\s*([0-9a-fA-F-]+)", body)
    return match.group(1) if match else None


class LemanaApiClient:
    def __init__(self, session: AsyncSession, context: PlpApiContext) -> None:
        self.session = session
        self.context = context

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://lemanapro.ru",
            "Referer": "https://lemanapro.ru/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "x-api-key": self.context.api_key,
        }
        if self.context.request_id:
            headers["x-request-id"] = self.context.request_id
        return headers

    def _url(self, method: str) -> str:
        # В API Лемана есть методы с двоеточием (`products:search`).
        # `urljoin` воспринимает такие строки как схему URL, поэтому путь собираем явно.
        return self.context.api_base_url.rstrip("/") + "/" + method.lstrip("/")

    async def _post(self, method: str, payload: dict, *, query: dict | None = None) -> dict:
        url = self._url(method)
        params = {"lang": "ru"}
        if query:
            params.update(query)

        headers = self._headers()
        last_status: int | None = None
        for attempt in range(1, CONFIG["api_max_retries"] + 1):
            log_api_request(
                method=method,
                url=url,
                params=params,
                headers=headers,
                payload=payload,
                attempt=attempt,
            )
            started_at = time.monotonic()
            response = await self.session.post(
                url,
                params=params,
                json=payload,
                headers=headers,
                timeout=CONFIG["catalog_timeout"],
            )
            elapsed_ms = int((time.monotonic() - started_at) * 1000)
            log_api_response(
                method=method,
                url=url,
                attempt=attempt,
                elapsed_ms=elapsed_ms,
                response=response,
            )
            last_status = response.status_code
            if response.status_code < 400:
                break

            qrator_blocked = _is_qrator_access_blocked(response)
            if qrator_blocked:
                support_id = _extract_qrator_support_id(response)
                logger.warning(
                    "%s: QRATOR Access Blocked, support_id=%s. "
                    "Не повторяем тот же payload, передаём batch в adaptive split.",
                    method,
                    support_id or "нет",
                )
                raise LemanaApiError(
                    f"{method}: QRATOR Access Blocked"
                    + (f" support_id={support_id}" if support_id else ""),
                    method=method,
                    status_code=response.status_code,
                    qrator_blocked=True,
                    support_id=support_id,
                )

            can_retry = response.status_code in {403, 429} or response.status_code >= 500
            if not can_retry or attempt >= CONFIG["api_max_retries"]:
                raise LemanaApiError(
                    f"{method}: HTTP {response.status_code}",
                    method=method,
                    status_code=response.status_code,
                )

            if response.status_code in {403, 429}:
                delay = CONFIG["api_antibot_cooldown"]
            else:
                delay = CONFIG["retry_backoff"] * attempt
            logger.warning(
                "%s: HTTP %s, повтор API через %.1f сек (attempt=%d/%d)",
                method,
                response.status_code,
                delay,
                attempt,
                CONFIG["api_max_retries"],
            )
            await asyncio.sleep(delay)
        else:
            raise LemanaApiError(
                f"{method}: HTTP {last_status}",
                method=method,
                status_code=last_status,
            )

        try:
            data = response.json()
        except Exception as exc:
            raise LemanaApiError(f"{method}: ответ не JSON", method=method) from exc
        if not isinstance(data, dict):
            raise LemanaApiError(
                f"{method}: ожидался JSON object, получен {type(data).__name__}",
                method=method,
            )
        return data

    def _search_payload(self, *, offset: int, sort_id: str | None = None) -> dict:
        payload = {
            "familyIds": [self.context.family_id],
            "limit": CONFIG["api_page_size"],
            "regionId": self.context.region_id,
            "facets": self.context.facets,
            "suggest": True,
            "filterByEligibility": True,
            "showComplects": True,
            "offset": offset,
            "customerId": "undefined",
            "parentFamilyId": None,
            "regionName": self.context.region_name,
            "searchMethod": self.context.search_method,
        }
        if sort_id:
            payload["sortId"] = sort_id
        return payload

    async def search_product_ids(
        self, *, offset: int, sort_id: str | None = None
    ) -> tuple[list[str], int]:
        data = await self._post(
            "products:search", self._search_payload(offset=offset, sort_id=sort_id)
        )
        product_ids = [str(product_id) for product_id in data.get("content") or []]
        total_count = int(data.get("totalCount") or 0)
        return product_ids, total_count

    async def get_products_data(
        self,
        product_ids: list[str],
        *,
        sort_id: str | None = None,
        include_facets: bool = True,
        filter_by_eligibility: bool = True,
        include_region: bool = True,
    ) -> list[dict]:
        if not product_ids:
            return []
        payload = {
            "productIds": product_ids,
            "filterByEligibility": filter_by_eligibility,
            "deliveryDate": False,
        }
        if include_region:
            payload["regionId"] = self.context.region_id
        if include_facets:
            payload["facets"] = self.context.facets
        if sort_id:
            payload["sortId"] = sort_id
        data = await self._post("products-data:search", payload)
        content = data.get("content") or []
        if not isinstance(content, list):
            raise LemanaApiError("products-data:search: content должен быть списком")
        return [item for item in content if isinstance(item, dict)]

    async def get_products_media(self, product_ids: list[str]) -> dict[str, dict]:
        if not product_ids:
            return {}
        payload = {"productIds": product_ids, "requestedMedia": ["image"]}
        data = await self._post("products-media:search", payload)
        media = data.get("data") or {}
        if not isinstance(media, dict):
            raise LemanaApiError("products-media:search: data должен быть объектом")
        return {str(key): value for key, value in media.items() if isinstance(value, dict)}
