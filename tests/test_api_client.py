import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from lemana_parser.api.client import LemanaApiClient
from lemana_parser.api.state import PlpApiContext
from lemana_parser.config import CONFIG


class ApiClientTests(unittest.TestCase):
    def _client(self, session=None):
        if session is None:
            session = object()
        return LemanaApiClient(
            session=session,
            context=PlpApiContext(
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
            ),
        )

    def test_builds_url_for_methods_with_colon(self):
        client = self._client()

        self.assertEqual(
            client._url("products:search"),
            "https://api.lemanapro.ru/hybrid/v1/products:search",
        )

    async def _fake_post(self, url, *, params=None, json=None, headers=None, timeout=None):
        self.last_payload = json
        return SimpleNamespace(status_code=200, json=lambda: {"content": []})

    def test_products_data_payload_can_omit_facets_and_region(self):
        session = SimpleNamespace(post=self._fake_post)
        client = self._client(session=session)

        import asyncio

        asyncio.run(
            client.get_products_data(
                ["111"],
                include_facets=False,
                filter_by_eligibility=False,
                include_region=False,
            )
        )

        self.assertEqual(self.last_payload["productIds"], ["111"])
        self.assertFalse(self.last_payload["filterByEligibility"])
        self.assertNotIn("facets", self.last_payload)
        self.assertNotIn("regionId", self.last_payload)

    def test_post_retries_api_pressure_status(self):
        class RetrySession:
            def __init__(self):
                self.calls = 0

            async def post(self, *args, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    return SimpleNamespace(status_code=403, json=lambda: {})
                return SimpleNamespace(status_code=200, json=lambda: {"content": []})

        session = RetrySession()
        client = self._client(session=session)
        old_retries = CONFIG["api_max_retries"]
        old_cooldown = CONFIG["api_antibot_cooldown"]
        CONFIG["api_max_retries"] = 2
        CONFIG["api_antibot_cooldown"] = 0
        try:
            import asyncio

            with patch("lemana_parser.api.client.asyncio.sleep", new=AsyncMock()):
                result = asyncio.run(client.get_products_data(["111"]))
        finally:
            CONFIG["api_max_retries"] = old_retries
            CONFIG["api_antibot_cooldown"] = old_cooldown

        self.assertEqual(result, [])
        self.assertEqual(session.calls, 2)


if __name__ == "__main__":
    unittest.main()
