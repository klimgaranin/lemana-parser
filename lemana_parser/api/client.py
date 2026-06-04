"""Тонкий клиент внутренних API каталога lemanapro.ru."""

from __future__ import annotations

import logging
from collections.abc import Iterable

from curl_cffi.requests import AsyncSession

from lemana_parser.api.metrics import record_api_status
from lemana_parser.api.state import PlpApiContext
from lemana_parser.config import CONFIG

logger = logging.getLogger("api.client")


class LemanaApiError(RuntimeError):
    """API lemanapro.ru вернул ошибку или неожиданный ответ."""


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


def _response_content_type(response) -> str:
    headers = getattr(response, "headers", {}) or {}
    return str(headers.get("content-type") or headers.get("Content-Type") or "")


def _trim_response_body(body: str, limit: int = 1000) -> str:
    body = " ".join((body or "").split())
    if len(body) <= limit:
        return body
    return body[:limit] + f"... <обрезано {len(body) - limit} символов>"


def chunked(items: list[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


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

        response = await self.session.post(
            url,
            params=params,
            json=payload,
            headers=self._headers(),
            timeout=CONFIG["catalog_timeout"],
        )
        record_api_status(method, response.status_code)
        if response.status_code >= 400:
            content_type = _response_content_type(response)
            body = _trim_response_body(_response_text(response))
            details = f"{method}: HTTP {response.status_code}"
            if content_type:
                details += f", content-type={content_type}"
            if body:
                details += f", body={body}"
            raise LemanaApiError(details)
        try:
            data = response.json()
        except Exception as exc:
            raise LemanaApiError(f"{method}: ответ не JSON") from exc
        if not isinstance(data, dict):
            raise LemanaApiError(f"{method}: ожидался JSON object, получен {type(data).__name__}")
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
