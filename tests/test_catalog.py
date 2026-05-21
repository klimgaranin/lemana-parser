import unittest
from unittest.mock import patch

from lemana_parser import catalog
from lemana_parser.config import CONFIG


class CatalogHelperTests(unittest.TestCase):
    def setUp(self):
        self.original_url = CONFIG["catalog_first_page_url"]

    def tearDown(self):
        CONFIG["catalog_first_page_url"] = self.original_url

    def test_build_page_url_adds_page_without_losing_query(self):
        CONFIG["catalog_first_page_url"] = (
            "https://lemanapro.ru/catalogue/test/?deliveryType=pickup&sort=price"
        )

        self.assertEqual(
            catalog._build_page_url(3),
            "https://lemanapro.ru/catalogue/test/?deliveryType=pickup&sort=price&page=3",
        )

    def test_build_page_url_replaces_existing_page(self):
        CONFIG["catalog_first_page_url"] = "https://lemanapro.ru/catalogue/test/?page=2&sort=price"

        self.assertEqual(
            catalog._build_page_url(5),
            "https://lemanapro.ru/catalogue/test/?page=5&sort=price",
        )

    def test_extract_catalog_items_regex_fallback(self):
        html = """
        <main>
          <div data-qa="products-list">
            <div data-qa="product" data-product-id="777888">
              <a href="/catalogue/fallback-product/777888/" aria-label="Fallback product"></a>
              <img src="https://img.example/fallback.webp">
              <span data-testid="price-integer" style="color:var(--text-primary)">3 500</span>
            </div>
          </div>
        </main>
        """

        with patch("lemana_parser.catalog._extract_catalog_items_dom", return_value=[]):
            items = catalog._extract_catalog_items(html, "https://lemanapro.ru")

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["article"], "777888")
        self.assertEqual(items[0]["url"], "https://lemanapro.ru/catalogue/fallback-product/777888/")
        self.assertEqual(items[0]["name"], "Fallback product")
        self.assertEqual(items[0]["price"], "3500,00")


if __name__ == "__main__":
    unittest.main()

