import unittest
from types import SimpleNamespace

from lemana_parser.api.gas_proxy import (
    fetch_catalog_page_via_gas,
    fetch_products_batch_via_gas,
)
from lemana_parser.api.state import PlpApiContext
from lemana_parser.config import CONFIG


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.last_payload = None

    async def post(self, url, *, json=None, headers=None, timeout=None, allow_redirects=None):
        self.last_payload = json
        self.last_url = url
        self.last_headers = headers
        self.last_timeout = timeout
        self.last_allow_redirects = allow_redirects
        return self.response


class GasProxyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.original_config = dict(CONFIG)
        CONFIG["gas_proxy_url"] = "https://script.google.com/macros/s/test/exec"
        CONFIG["gas_proxy_token"] = "secret"
        CONFIG["api_fallback_region_ids"] = "35, 36"

    def tearDown(self):
        CONFIG.clear()
        CONFIG.update(self.original_config)

    def _context(self):
        return PlpApiContext(
            api_base_url="https://api.lemanapro.ru/hybrid/v1/",
            api_key="key",
            request_id="request",
            region_id="34",
            region_code="moscow",
            region_name="Москва",
            family_id="family",
            search_method="CATEGORY",
            facets=[{"id": "deliveryType", "values": ["Самовывоз"]}],
            initial_product_ids=[],
            total_count=0,
        )

    async def test_sends_context_and_product_ids_to_gas_proxy(self):
        response = SimpleNamespace(
            status_code=200,
            headers={"content-type": "application/json"},
            text='{"ok":true,"productsData":[{"productId":"111"}],"mediaMap":{"111":{}},"logs":[]}',
            json=lambda: {
                "ok": True,
                "productsData": [{"productId": "111"}],
                "mediaMap": {"111": {}},
                "logs": [],
            },
        )
        session = FakeSession(response)

        products_data, media_map = await fetch_products_batch_via_gas(
            session,
            self._context(),
            ["111"],
            articles_mode="relaxed",
        )

        self.assertEqual(products_data, [{"productId": "111"}])
        self.assertEqual(media_map, {"111": {}})
        self.assertEqual(session.last_url, CONFIG["gas_proxy_url"])
        self.assertEqual(session.last_payload["action"], "productsBatch")
        self.assertEqual(session.last_payload["token"], "secret")
        self.assertEqual(session.last_payload["productIds"], ["111"])
        self.assertEqual(session.last_payload["articlesMode"], "relaxed")
        self.assertEqual(session.last_payload["context"]["apiKey"], "key")
        self.assertEqual(session.last_payload["context"]["familyId"], "family")
        self.assertEqual(session.last_payload["fallbackRegionIds"], ["35", "36"])

    async def test_sends_catalog_page_request_to_gas_proxy(self):
        response = SimpleNamespace(
            status_code=200,
            headers={"content-type": "application/json"},
            text='{"ok":true,"productIds":["111"],"totalCount":1,"productsData":[{"productId":"111"}],"mediaMap":{},"logs":[]}',
            json=lambda: {
                "ok": True,
                "productIds": ["111"],
                "totalCount": 1,
                "productsData": [{"productId": "111"}],
                "mediaMap": {},
                "logs": [],
            },
        )
        session = FakeSession(response)

        product_ids, total_count, products_data, media_map = await fetch_catalog_page_via_gas(
            session,
            self._context(),
            offset=100,
        )

        self.assertEqual(product_ids, ["111"])
        self.assertEqual(total_count, 1)
        self.assertEqual(products_data, [{"productId": "111"}])
        self.assertEqual(media_map, {})
        self.assertEqual(session.last_payload["action"], "catalogPage")
        self.assertEqual(session.last_payload["offset"], 100)
        self.assertEqual(session.last_payload["limit"], CONFIG["api_page_size"])
        self.assertEqual(session.last_payload["fallbackRegionIds"], ["35", "36"])

    async def test_raises_on_gas_proxy_error_body(self):
        response = SimpleNamespace(
            status_code=200,
            headers={"content-type": "application/json"},
            text='{"ok":false,"error":"blocked","logs":[{"statusCode":403}]}',
            json=lambda: {"ok": False, "error": "blocked", "logs": [{"statusCode": 403}]},
        )
        session = FakeSession(response)

        with self.assertRaisesRegex(Exception, "blocked"):
            await fetch_products_batch_via_gas(
                session,
                self._context(),
                ["111"],
                articles_mode="relaxed",
            )


if __name__ == "__main__":
    unittest.main()
