"""Проверка работоспособности cookie перед запуском парсинга."""

import logging
import re
from dataclasses import dataclass
from urllib.parse import urljoin

from curl_cffi.requests import Session as CurlSession

from lemana_parser.config import CONFIG
from lemana_parser.http_utils import build_headers, parse_cookie_header

logger = logging.getLogger("cookie_health")


@dataclass(frozen=True)
class CookieCheckResult:
    ok: bool
    reason: str
    catalog_status: int | None = None
    product_status: int | None = None
    catalog_cards: int = 0
    product_url: str = ""


def _extract_first_product_url(html: str, base_url: str) -> str:
    match = re.search(r'href=["\']([^"\']*/product/[^"\']+)["\']', html, re.I)
    if not match:
        match = re.search(r'href=["\']([^"\']*/catalogue/[^"\']+)["\']', html, re.I)
    return urljoin(base_url, match.group(1)) if match else ""


def _count_catalog_cards(html: str) -> int:
    return len(re.findall(r'data-product-id=["\']([^"\']+)["\']', html))


def check_cookie_sync(
    url: str,
    cookie: str,
    *,
    check_product: bool = True,
) -> CookieCheckResult:
    """Проверяет каталог и, если нужно, первую карточку товара."""
    if not cookie:
        return CookieCheckResult(False, "LEMANA_COOKIE пустой")

    try:
        with CurlSession(
            impersonate=CONFIG["browser_impersonate"],
            verify=False,
            cookies=parse_cookie_header(cookie),
        ) as session:
            catalog_resp = session.get(
                url,
                headers=build_headers(),
                timeout=CONFIG["catalog_timeout"],
                allow_redirects=True,
            )
            catalog_html = catalog_resp.text or ""
            catalog_cards = _count_catalog_cards(catalog_html)

            if catalog_resp.status_code in {401, 403, 429}:
                return CookieCheckResult(
                    False,
                    f"каталог вернул HTTP {catalog_resp.status_code}",
                    catalog_status=catalog_resp.status_code,
                    catalog_cards=catalog_cards,
                )

            if catalog_resp.status_code >= 400:
                return CookieCheckResult(
                    False,
                    f"каталог вернул HTTP {catalog_resp.status_code}",
                    catalog_status=catalog_resp.status_code,
                    catalog_cards=catalog_cards,
                )

            if not check_product:
                return CookieCheckResult(
                    True,
                    "каталог доступен",
                    catalog_status=catalog_resp.status_code,
                    catalog_cards=catalog_cards,
                )

            product_url = _extract_first_product_url(catalog_html, url)
            if not product_url:
                return CookieCheckResult(
                    False,
                    "каталог открылся, но ссылка на первую карточку не найдена",
                    catalog_status=catalog_resp.status_code,
                    catalog_cards=catalog_cards,
                )

            product_resp = session.get(
                product_url,
                headers=build_headers(extra_headers={"Referer": url}),
                timeout=CONFIG["product_timeout"],
                allow_redirects=True,
            )

            if product_resp.status_code in {401, 403, 429}:
                return CookieCheckResult(
                    False,
                    f"первая карточка вернула HTTP {product_resp.status_code}",
                    catalog_status=catalog_resp.status_code,
                    product_status=product_resp.status_code,
                    catalog_cards=catalog_cards,
                    product_url=product_url,
                )

            if product_resp.status_code >= 400:
                return CookieCheckResult(
                    False,
                    f"первая карточка вернула HTTP {product_resp.status_code}",
                    catalog_status=catalog_resp.status_code,
                    product_status=product_resp.status_code,
                    catalog_cards=catalog_cards,
                    product_url=product_url,
                )

            return CookieCheckResult(
                True,
                "каталог и первая карточка доступны",
                catalog_status=catalog_resp.status_code,
                product_status=product_resp.status_code,
                catalog_cards=catalog_cards,
                product_url=product_url,
            )
    except Exception as exc:
        logger.warning("Ошибка проверки cookie: %s: %s", type(exc).__name__, exc)
        return CookieCheckResult(False, f"ошибка проверки: {type(exc).__name__}: {exc}")
