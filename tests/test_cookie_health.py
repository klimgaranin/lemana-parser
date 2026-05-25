import unittest
from unittest.mock import patch

from lemana_parser.auth.cookie_health import check_cookie_sync


class FakeResponse:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, *args, **kwargs):
        return self.responses.pop(0)


class CookieHealthTests(unittest.TestCase):
    def test_empty_cookie_is_not_ok(self):
        result = check_cookie_sync("https://lemanapro.ru/catalogue/test/", "")

        self.assertFalse(result.ok)
        self.assertIn("пустой", result.reason)

    def test_catalog_401_is_not_ok(self):
        fake_session = FakeSession([FakeResponse(401, "denied")])

        with patch("lemana_parser.auth.cookie_health.CurlSession", return_value=fake_session):
            result = check_cookie_sync("https://lemanapro.ru/catalogue/test/", "qrator_jsid2=abc")

        self.assertFalse(result.ok)
        self.assertEqual(result.catalog_status, 401)

    def test_catalog_and_product_200_are_ok(self):
        catalog_html = """
        <div data-product-id="123">
          <a href="/product/test-product-123/">Товар</a>
        </div>
        """
        fake_session = FakeSession(
            [
                FakeResponse(200, catalog_html),
                FakeResponse(200, "<html>product</html>"),
            ]
        )

        with patch("lemana_parser.auth.cookie_health.CurlSession", return_value=fake_session):
            result = check_cookie_sync("https://lemanapro.ru/catalogue/test/", "qrator_jsid2=abc")

        self.assertTrue(result.ok)
        self.assertEqual(result.catalog_status, 200)
        self.assertEqual(result.product_status, 200)
        self.assertEqual(result.catalog_cards, 1)

    def test_product_403_is_not_ok(self):
        catalog_html = '<a href="/product/test-product-123/">Товар</a>'
        fake_session = FakeSession(
            [
                FakeResponse(200, catalog_html),
                FakeResponse(403, "blocked"),
            ]
        )

        with patch("lemana_parser.auth.cookie_health.CurlSession", return_value=fake_session):
            result = check_cookie_sync("https://lemanapro.ru/catalogue/test/", "qrator_jsid2=abc")

        self.assertFalse(result.ok)
        self.assertEqual(result.product_status, 403)


if __name__ == "__main__":
    unittest.main()
