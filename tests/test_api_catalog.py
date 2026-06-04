import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from lemana_parser.api.catalog_api import (
    _load_products_batch,
    fetch_catalog_products_api,
    fetch_products_by_articles_api,
)
from lemana_parser.api.client import LemanaApiError
from lemana_parser.api.gas_proxy import LemanaGasProxyError
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
        old_transport = CONFIG["api_transport"]
        CONFIG["api_page_size"] = 1
        CONFIG["api_articles_sleep"] = 3
        CONFIG["api_transport"] = "local"
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
            CONFIG["api_transport"] = old_transport

        self.assertEqual(len(products), 2)
        sleep_mock.assert_awaited_once_with(3)

    async def test_articles_gas_transport_uses_proxy_batch(self):
        old_page_size = CONFIG["api_page_size"]
        old_transport = CONFIG["api_transport"]
        CONFIG["api_page_size"] = 2
        CONFIG["api_transport"] = "gas"
        try:
            with (
                patch("lemana_parser.api.catalog_api.load_api_context", return_value=object()),
                patch(
                    "lemana_parser.api.catalog_api.fetch_products_batch_via_gas",
                    new=AsyncMock(
                        return_value=(
                            [
                                {
                                    "productId": "111",
                                    "displayedName": "GAS товар",
                                    "productLink": "/product/gas/",
                                    "price": {"main_price": 10},
                                    "characteristics": [],
                                }
                            ],
                            {"111": {"images": [{"url": "https://img.example/gas.jpg"}]}},
                        )
                    ),
                ) as gas_mock,
            ):
                products, _ = await fetch_products_by_articles_api(object(), ["111", "222"])
        finally:
            CONFIG["api_page_size"] = old_page_size
            CONFIG["api_transport"] = old_transport

        self.assertEqual(products[0]["status"], "ok")
        self.assertEqual(products[0]["article"], "111")
        self.assertEqual(products[1]["status"], "api_data_missing")
        gas_mock.assert_awaited_once()

    async def test_articles_gas_fallback_uses_local_batch_on_proxy_error(self):
        old_page_size = CONFIG["api_page_size"]
        old_transport = CONFIG["api_transport"]
        CONFIG["api_page_size"] = 1
        CONFIG["api_transport"] = "gas-fallback"
        try:
            with (
                patch("lemana_parser.api.catalog_api.load_api_context", return_value=object()),
                patch(
                    "lemana_parser.api.catalog_api.LemanaApiClient",
                    return_value=FakeApiClient(),
                ),
                patch(
                    "lemana_parser.api.catalog_api.fetch_products_batch_via_gas",
                    new=AsyncMock(side_effect=LemanaGasProxyError("blocked")),
                ) as gas_mock,
            ):
                products, _ = await fetch_products_by_articles_api(object(), ["111"])
        finally:
            CONFIG["api_page_size"] = old_page_size
            CONFIG["api_transport"] = old_transport

        self.assertEqual(products[0]["status"], "ok")
        self.assertEqual(products[0]["article"], "111")
        gas_mock.assert_awaited_once()

    async def test_catalog_gas_transport_uses_proxy_page(self):
        old_page_size = CONFIG["api_page_size"]
        old_transport = CONFIG["api_transport"]
        old_max_products = CONFIG["max_products"]
        old_catalog_concurrency = CONFIG["api_catalog_concurrency"]
        CONFIG["api_page_size"] = 100
        CONFIG["api_transport"] = "gas"
        CONFIG["max_products"] = 1
        CONFIG["api_catalog_concurrency"] = 1
        try:
            with (
                patch(
                    "lemana_parser.api.catalog_api.load_api_context",
                    return_value=SimpleNamespace(total_count=1),
                ),
                patch(
                    "lemana_parser.api.catalog_api.fetch_catalog_page_via_gas",
                    new=AsyncMock(
                        return_value=(
                            ["111"],
                            1,
                            [
                                {
                                    "productId": "111",
                                    "displayedName": "GAS каталог",
                                    "productLink": "/product/catalog-gas/",
                                    "price": {"main_price": 20},
                                    "characteristics": [],
                                }
                            ],
                            {"111": {"images": [{"url": "https://img.example/catalog.jpg"}]}},
                        )
                    ),
                ) as gas_mock,
            ):
                products, _ = await fetch_catalog_products_api(object())
        finally:
            CONFIG["api_page_size"] = old_page_size
            CONFIG["api_transport"] = old_transport
            CONFIG["max_products"] = old_max_products
            CONFIG["api_catalog_concurrency"] = old_catalog_concurrency

        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["status"], "ok")
        self.assertEqual(products[0]["article"], "111")
        gas_mock.assert_awaited_once()

    async def test_parallel_catalog_keeps_offset_order(self):
        old_page_size = CONFIG["api_page_size"]
        old_transport = CONFIG["api_transport"]
        old_max_products = CONFIG["max_products"]
        old_catalog_concurrency = CONFIG["api_catalog_concurrency"]
        CONFIG["api_page_size"] = 1
        CONFIG["api_transport"] = "gas"
        CONFIG["max_products"] = 3
        CONFIG["api_catalog_concurrency"] = 2

        async def fake_load_page(session, context, client, *, offset):
            if offset == 0:
                await asyncio.sleep(0.01)
            return (
                offset,
                [str(offset)],
                3,
                [
                    {
                        "status": "ok",
                        "article": str(offset),
                        "url": f"https://example.test/{offset}",
                        "name": f"Товар {offset}",
                        "price": offset,
                        "image": "",
                        "characteristics": {"Порядок": str(offset)},
                    }
                ],
            )

        try:
            with (
                patch(
                    "lemana_parser.api.catalog_api.load_api_context",
                    return_value=SimpleNamespace(total_count=3),
                ),
                patch(
                    "lemana_parser.api.catalog_api._load_catalog_page",
                    new=fake_load_page,
                ),
            ):
                products, char_keys = await fetch_catalog_products_api(object())
        finally:
            CONFIG["api_page_size"] = old_page_size
            CONFIG["api_transport"] = old_transport
            CONFIG["max_products"] = old_max_products
            CONFIG["api_catalog_concurrency"] = old_catalog_concurrency

        self.assertEqual([product["article"] for product in products], ["0", "1", "2"])
        self.assertEqual(char_keys, ["Порядок"])


if __name__ == "__main__":
    unittest.main()
