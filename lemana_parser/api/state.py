"""Извлечение API-настроек из HTML состояния PLP."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from lemana_parser.config import CONFIG


class PlpStateError(ValueError):
    """HTML страницы каталога не содержит ожидаемое состояние PLP."""


@dataclass(frozen=True)
class PlpApiContext:
    api_base_url: str
    api_key: str
    request_id: str
    region_id: str
    region_code: str
    region_name: str
    family_id: str
    search_method: str
    facets: list[dict[str, list[str]]]
    initial_product_ids: list[str]
    total_count: int


def _extract_balanced_json(text: str, start: int) -> str:
    depth = 0
    in_string = False
    escaped = False

    for pos in range(start, len(text)):
        char = text[pos]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : pos + 1]

    raise PlpStateError("INITIAL_STATE найден, но JSON не завершён")


def extract_plp_initial_state(html: str) -> dict:
    marker = 'window.INITIAL_STATE["plp"]'
    marker_pos = (html or "").find(marker)
    if marker_pos < 0:
        raise PlpStateError('не найден window.INITIAL_STATE["plp"]')

    start = html.find("{", marker_pos)
    if start < 0:
        raise PlpStateError('не найден JSON после window.INITIAL_STATE["plp"]')

    try:
        return json.loads(_extract_balanced_json(html, start))
    except json.JSONDecodeError as exc:
        raise PlpStateError(f"INITIAL_STATE содержит невалидный JSON: {exc}") from exc


def _cookies_from_state(plp_state: dict) -> dict:
    cookies = plp_state.get("cookies") or {}
    if isinstance(cookies.get("cookies"), dict):
        return cookies["cookies"]
    return cookies if isinstance(cookies, dict) else {}


def _facets_from_url(url: str) -> list[dict[str, list[str]]]:
    ignored = {"page", "utm_referrer"}
    query = parse_qs(urlsplit(url).query, keep_blank_values=False)
    facets = []
    for key, values in query.items():
        if key in ignored or not values:
            continue
        facets.append({"id": key, "values": values})
    return facets


def _validate_api_base_url(api_base_url: str) -> None:
    parsed = urlsplit(api_base_url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host:
        raise PlpStateError("ORCHESTRATOR_HOST должен быть HTTPS URL")
    if host != "api.lemanapro.ru" and not host.endswith(".lemanapro.ru"):
        raise PlpStateError("ORCHESTRATOR_HOST должен указывать на домен lemanapro.ru")


def build_plp_api_context(html: str, catalog_url: str) -> PlpApiContext:
    state = extract_plp_initial_state(html)
    plp_root = state.get("plp") or {}
    env = plp_root.get("env") or {}
    products_state = (plp_root.get("plp") or {}).get("products") or {}
    cookies = _cookies_from_state(plp_root)

    api_base_url = (env.get("ORCHESTRATOR_HOST") or "").strip()
    api_key = (env.get("apiKey") or env.get("API_KEY") or "").strip()
    family_id = str(products_state.get("familyId") or "").strip()

    if not api_base_url:
        raise PlpStateError("в INITIAL_STATE не найден ORCHESTRATOR_HOST")
    _validate_api_base_url(api_base_url)
    if not api_key:
        raise PlpStateError("в INITIAL_STATE не найден apiKey")
    if not family_id:
        raise PlpStateError("в INITIAL_STATE не найден products.familyId")

    return PlpApiContext(
        api_base_url=api_base_url.rstrip("/") + "/",
        api_key=api_key,
        request_id=str(env.get("requestID") or env.get("requestId") or ""),
        region_id=str(cookies.get("_regionID") or "34"),
        region_code=str(cookies.get("_userRegion") or "moscow"),
        region_name=CONFIG["api_region_name"],
        family_id=family_id,
        search_method=str(products_state.get("searchMethod") or "DEFAULT"),
        facets=_facets_from_url(catalog_url),
        initial_product_ids=[str(x) for x in products_state.get("productsIds") or []],
        total_count=int(products_state.get("productsCount") or 0),
    )
