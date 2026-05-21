import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from lemana_parser.catalog import _extract_catalog_items
from lemana_parser.parsers.html import (
    extract_all_characteristics,
    extract_main_image,
    parse_price_from_html,
)
from lemana_parser.products import _fetch_product, _parse_product, summarize_products


class ParserTests(unittest.TestCase):
    def test_extract_catalog_items_from_dom(self):
        html = """
        <main>
          <div data-qa="products-list">
            <div data-qa="product" data-product-id="123456">
              <a href="/catalogue/test-product/123456/" aria-label="Fallback name">
                <span data-qa="product-name">Светильник настенный</span>
              </a>
              <img itemprop="image" src="https://img.example/p.webp">
              <span data-testid="price-integer" style="color:var(--text-primary)">1 299</span>
            </div>
          </div>
          <div data-qa="pagination"><a href="?page=2">2</a></div>
        </main>
        """

        items = _extract_catalog_items(html, "https://lemanapro.ru")

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["article"], "123456")
        self.assertEqual(items[0]["url"], "https://lemanapro.ru/catalogue/test-product/123456/")
        self.assertEqual(items[0]["name"], "Светильник настенный")
        self.assertEqual(items[0]["price"], "1299,00")
        self.assertEqual(items[0]["image"], "https://img.example/p.webp")

    def test_product_fields_from_dom(self):
        html = """
        <html>
          <head><meta property="og:image" content="https://img.example/main.jpg"></head>
          <body>
            <h1>Карточка товара</h1>
            <span data-testid="price-integer" style="color:var(--text-primary)">2 349</span>
            <span data-testid="price-fraction">50</span>
            <section id="characteristics">
              <div data-qa="characteristics-list-item">
                <div>Материал</div><div>Металл</div>
              </div>
              <div data-qa="characteristics-list-item">
                <div>Цвет</div><div>Белый</div>
              </div>
            </section>
          </body>
        </html>
        """

        product = _parse_product(html, {"url": "https://lemanapro.ru/catalogue/x/987654/"})

        self.assertEqual(product["status"], "ok")
        self.assertEqual(product["error"], "")
        self.assertEqual(product["article"], "987654")
        self.assertEqual(product["name"], "Карточка товара")
        self.assertEqual(product["price"], "2349,50")
        self.assertEqual(product["image"], "https://img.example/main.jpg")
        self.assertEqual(product["characteristics"]["Материал"], "Металл")
        self.assertEqual(product["characteristics"]["Цвет"], "Белый")

    def test_utils_dom_parsers(self):
        html = """
        <meta property="og:image" content="https://img.example/one.webp">
        <span data-testid="price-integer" style="color:var(--text-primary)">10 000</span>
        <span data-testid="price-decimal">7</span>
        <div data-qa="characteristics-list-item"><div>Высота</div><div>10 см</div></div>
        """

        self.assertEqual(parse_price_from_html(html), "10000,70")
        self.assertEqual(extract_main_image(html), "https://img.example/one.webp")
        self.assertEqual(extract_all_characteristics(html), {"Высота": "10 см"})

    def test_summarize_products_counts_statuses(self):
        summary = summarize_products(
            [
                {"status": "ok"},
                {"status": "fetch_failed"},
                {"status": "parse_empty"},
                {},
            ]
        )

        self.assertEqual(summary["total"], 4)
        self.assertEqual(summary["ok"], 2)
        self.assertEqual(summary["errors"], 2)
        self.assertEqual(
            summary["status_counts"],
            {"fetch_failed": 1, "ok": 2, "parse_empty": 1},
        )


class ProductFetchTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_product_returns_failed_status_on_empty_response(self):
        with patch("lemana_parser.products.fetch_with_retry", new=AsyncMock(return_value=None)):
            product = await _fetch_product(
                object(),
                {
                    "article": "123456",
                    "url": "https://lemanapro.ru/catalogue/x/123456/",
                    "name": "Название из каталога",
                    "price": "100,00",
                    "image": "https://img.example/catalog.webp",
                },
                sem=asyncio.Semaphore(1),
            )

        self.assertEqual(product["status"], "fetch_failed")
        self.assertEqual(product["article"], "123456")
        self.assertEqual(product["name"], "Название из каталога")
        self.assertIn("Не удалось загрузить", product["error"])


if __name__ == "__main__":
    unittest.main()
