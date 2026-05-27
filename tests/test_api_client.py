import unittest

from lemana_parser.api.client import LemanaApiClient
from lemana_parser.api.state import PlpApiContext


class ApiClientTests(unittest.TestCase):
    def test_builds_url_for_methods_with_colon(self):
        client = LemanaApiClient(
            session=object(),
            context=PlpApiContext(
                api_base_url="https://api.lemanapro.ru/hybrid/v1/",
                api_key="key",
                request_id="request",
                region_id="34",
                region_code="moscow",
                region_name="Москва",
                family_id="family",
                search_method="CATEGORY",
                facets=[],
                initial_product_ids=[],
                total_count=0,
            ),
        )

        self.assertEqual(
            client._url("products:search"),
            "https://api.lemanapro.ru/hybrid/v1/products:search",
        )


if __name__ == "__main__":
    unittest.main()

