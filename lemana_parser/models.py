"""Shared typed data structures for parser modules."""

from typing import TypedDict


class CatalogItem(TypedDict, total=False):
    article: str
    url: str
    name: str
    price: str
    image: str


class Product(TypedDict, total=False):
    status: str
    error: str
    article: str
    url: str
    name: str
    price: str
    image: str
    characteristics: dict[str, str]


class ProductSummary(TypedDict):
    total: int
    ok: int
    errors: int
    status_counts: dict[str, int]

