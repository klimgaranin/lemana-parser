"""Нормализация ответов API lemanapro.ru в внутренние модели проекта."""

from __future__ import annotations

from lemana_parser.models import Product

LEMANA_BASE_URL = "https://lemanapro.ru"


def format_api_price(price: dict | None) -> str:
    if not isinstance(price, dict):
        return ""
    value = price.get("main_price")
    if value is None:
        return ""
    try:
        return f"{float(value):.2f}".replace(".", ",")
    except (TypeError, ValueError):
        return str(value)


def normalize_product_url(product_link: str) -> str:
    if not product_link:
        return ""
    if product_link.startswith("http://") or product_link.startswith("https://"):
        return product_link
    return LEMANA_BASE_URL + (product_link if product_link.startswith("/") else "/" + product_link)


def normalize_characteristics(raw_characteristics: object) -> dict[str, str]:
    if not isinstance(raw_characteristics, list):
        return {}

    result: dict[str, str] = {}
    for item in raw_characteristics:
        if not isinstance(item, dict):
            continue
        label = str(item.get("description") or item.get("name") or "").strip()
        value = str(item.get("value") or "").strip()
        if label and value and label not in result:
            result[label] = value
    return result


def extract_media_image(product_data: dict, media_data: dict | None = None) -> str:
    media_data = media_data if isinstance(media_data, dict) else {}
    images = media_data.get("images")
    if isinstance(images, list):
        for image in images:
            if isinstance(image, dict) and image.get("url"):
                return str(image["url"])

    main_photo = product_data.get("mediaMainPhoto")
    if isinstance(main_photo, dict):
        return str(main_photo.get("desktop") or main_photo.get("tablet") or main_photo.get("mobile") or "")
    return ""


def normalize_api_product(product_data: dict, media_data: dict | None = None) -> Product:
    product_id = str(product_data.get("productId") or "").strip()
    return {
        "status": "ok",
        "error": "",
        "article": product_id,
        "url": normalize_product_url(str(product_data.get("productLink") or "")),
        "name": str(product_data.get("displayedName") or "").strip(),
        "price": format_api_price(product_data.get("price")),
        "image": extract_media_image(product_data, media_data),
        "characteristics": normalize_characteristics(product_data.get("characteristics")),
    }

