import unittest

from lemana_parser.api.catalog_api import _load_products_batch
from lemana_parser.api.client import LemanaApiError


class FakeApiClient:
    async def get_products_data(self, product_ids, *, sort_id=None):
        return [
            {
                "productId": product_ids[0],
                "displayedName": "Товар 1",
                "productLink": "/product/test-1/",
                "price": {"main_price": 123.4},
                "characteristics": [{"description": "Цвет", "value": "белый"}],
            }
        ]

    async def get_products_media(self, product_ids):
        return {product_ids[0]: {"images": [{"url": "https://img.example/test.jpg"}]}}


class FakeMediaFailClient(FakeApiClient):
    async def get_products_media(self, product_ids):
        raise LemanaApiError("media failed")


class ApiCatalogTests(unittest.IsolatedAsyncioTestCase):
    async def test_load_products_batch_marks_missing_product_data(self):
        products = await _load_products_batch(FakeApiClient(), ["111", "222"])

        self.assertEqual(products[0]["status"], "ok")
        self.assertEqual(products[0]["article"], "111")
        self.assertEqual(products[1]["status"], "api_data_missing")
        self.assertEqual(products[1]["article"], "222")

    async def test_load_products_batch_survives_media_failure(self):
        products = await _load_products_batch(FakeMediaFailClient(), ["111"])

        self.assertEqual(products[0]["status"], "ok")
        self.assertEqual(products[0]["article"], "111")


if __name__ == "__main__":
    unittest.main()
