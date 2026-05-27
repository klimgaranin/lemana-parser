import unittest

from lemana_parser.api.state import PlpStateError, build_plp_api_context


class ApiStateTests(unittest.TestCase):
    def test_builds_context_from_plp_initial_state(self):
        html = """
        <script>
        window.INITIAL_STATE["plp"]={
          "version":"1",
          "plp":{
            "plp":{
              "products":{
                "familyId":"family-1",
                "productsIds":["111","222"],
                "productsCount":2,
                "searchMethod":"CATEGORY"
              }
            },
            "env":{
              "ORCHESTRATOR_HOST":"https://api.lemanapro.ru/hybrid/v1/",
              "apiKey":"secret-key",
              "requestID":"request-1"
            },
            "cookies":{
              "cookies":{
                "_regionID":"34",
                "_userRegion":"moscow"
              }
            }
          }
        }
        </script>
        """

        context = build_plp_api_context(
            html,
            "https://lemanapro.ru/catalogue/test/?deliveryType=Самовывоз+в+магазине&page=2",
        )

        self.assertEqual(context.api_base_url, "https://api.lemanapro.ru/hybrid/v1/")
        self.assertEqual(context.api_key, "secret-key")
        self.assertEqual(context.request_id, "request-1")
        self.assertEqual(context.region_id, "34")
        self.assertEqual(context.region_code, "moscow")
        self.assertEqual(context.family_id, "family-1")
        self.assertEqual(context.initial_product_ids, ["111", "222"])
        self.assertEqual(context.total_count, 2)
        self.assertEqual(
            context.facets, [{"id": "deliveryType", "values": ["Самовывоз в магазине"]}]
        )

    def test_rejects_non_lemana_api_host(self):
        html = """
        <script>
        window.INITIAL_STATE["plp"]={
          "plp":{
            "plp":{"products":{"familyId":"family-1"}},
            "env":{
              "ORCHESTRATOR_HOST":"https://example.com/hybrid/v1/",
              "apiKey":"secret-key"
            },
            "cookies":{"cookies":{"_regionID":"34"}}
          }
        }
        </script>
        """

        with self.assertRaisesRegex(PlpStateError, "домен lemanapro.ru"):
            build_plp_api_context(html, "https://lemanapro.ru/catalogue/test/")


if __name__ == "__main__":
    unittest.main()
