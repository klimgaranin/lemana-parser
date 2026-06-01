import unittest
from unittest.mock import AsyncMock, patch

from lemana_parser.api.catalog_api import _load_products_batch, fetch_products_by_articles_api
from lemana_parser.api.client import LemanaApiError
from lemana_parser.config import CONFIG


class FakeApiClient:
    async def get_products_data(
        self,
        product_ids,
        *,
        sort_id=None,
        include_facets=True,
        filter_by_eligibility=True,
        include_region=True,
    ):
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


class FakeRelaxedClient(FakeApiClient):
    def __init__(self):
        self.calls = []

    async def get_products_data(
        self,
        product_ids,
        *,
        sort_id=None,
        include_facets=True,
        filter_by_eligibility=True,
        include_region=True,
    ):
        self.calls.append(
            {
                "product_ids": product_ids,
                "include_facets": include_facets,
                "filter_by_eligibility": filter_by_eligibility,
                "include_region": include_region,
            }
        )
        if include_facets:
            return []
        return [
            {
                "productId": product_ids[0],
                "displayedName": "Товар после relaxed retry",
                "productLink": "/product/test-relaxed/",
                "price": {"main_price": 99},
                "characteristics": [],
            }
        ]


class FakeAlwaysMissingClient(FakeRelaxedClient):
    async def get_products_data(
        self,
        product_ids,
        *,
        sort_id=None,
        include_facets=True,
        filter_by_eligibility=True,
        include_region=True,
    ):
        self.calls.append(
            {
                "product_ids": product_ids,
                "include_facets": include_facets,
                "filter_by_eligibility": filter_by_eligibility,
                "include_region": include_region,
            }
        )
        return []


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

    async def test_load_products_batch_recovers_missing_articles_with_relaxed_retry(self):
        client = FakeRelaxedClient()

        products = await _load_products_batch(client, ["111"], relaxed_missing_retry=True)

        self.assertEqual(products[0]["status"], "ok")
        self.assertEqual(products[0]["article"], "111")
        self.assertEqual(len(client.calls), 2)
        self.assertFalse(client.calls[1]["include_facets"])
        self.assertFalse(client.calls[1]["filter_by_eligibility"])
        self.assertTrue(client.calls[1]["include_region"])

    async def test_relaxed_retry_does_not_repeat_without_region(self):
        client = FakeAlwaysMissingClient()

        products = await _load_products_batch(client, ["111"], relaxed_missing_retry=True)

        self.assertEqual(products[0]["status"], "api_data_missing")
        self.assertEqual(len(client.calls), 2)
        self.assertTrue(all(call["include_region"] for call in client.calls))

    async def test_articles_relaxed_mode_starts_without_facets_and_eligibility(self):
        client = FakeRelaxedClient()

        products = await _load_products_batch(
            client,
            ["111"],
            relaxed_missing_retry=True,
            articles_mode="relaxed",
        )

        self.assertEqual(products[0]["status"], "ok")
        self.assertEqual(len(client.calls), 1)
        self.assertFalse(client.calls[0]["include_facets"])
        self.assertFalse(client.calls[0]["filter_by_eligibility"])
        self.assertTrue(client.calls[0]["include_region"])

    async def test_articles_api_sleep_runs_between_batches_only(self):
        old_page_size = CONFIG["api_page_size"]
        old_sleep = CONFIG["api_articles_sleep"]
        CONFIG["api_page_size"] = 1
        CONFIG["api_articles_sleep"] = 3
        try:
            with (
                patch("lemana_parser.api.catalog_api.load_api_context", return_value=object()),
                patch(
                    "lemana_parser.api.catalog_api.LemanaApiClient",
                    return_value=FakeApiClient(),
                ),
                patch("lemana_parser.api.catalog_api.asyncio.sleep", new=AsyncMock()) as sleep_mock,
            ):
                products, _ = await fetch_products_by_articles_api(object(), ["111", "222"])
        finally:
            CONFIG["api_page_size"] = old_page_size
            CONFIG["api_articles_sleep"] = old_sleep

        self.assertEqual(len(products), 2)
        sleep_mock.assert_awaited_once_with(3)


if __name__ == "__main__":
    unittest.main()
