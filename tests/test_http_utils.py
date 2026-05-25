import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from lemana_parser.config import CONFIG
from lemana_parser.http_utils import (
    build_headers,
    fetch_with_retry,
    fetch_with_retry_result,
    parse_cookie_header,
)


class FakeResponse:
    def __init__(self, status_code: int, text: str = "x" * 250):
        self.status_code = status_code
        self.text = text
        self.headers = {"content-type": "text/html"}
        self.url = "https://lemanapro.ru/catalogue/test/"


class HttpUtilsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.original_cookie = CONFIG["cookie"]
        self.original_max_retries = CONFIG["max_retries"]
        self.original_retry_backoff = CONFIG["retry_backoff"]

    def tearDown(self):
        CONFIG["cookie"] = self.original_cookie
        CONFIG["max_retries"] = self.original_max_retries
        CONFIG["retry_backoff"] = self.original_retry_backoff

    def test_build_headers_uses_cookie_and_extra_headers(self):
        headers = build_headers(
            cookie="a=b",
            extra_headers={"Referer": "https://lemanapro.ru/catalogue/"},
        )

        self.assertEqual(headers["Cookie"], "a=b")
        self.assertEqual(headers["Referer"], "https://lemanapro.ru/catalogue/")
        self.assertIn("Accept-Language", headers)
        self.assertEqual(headers["Sec-Fetch-Dest"], "document")

    def test_build_headers_does_not_force_config_cookie_by_default(self):
        CONFIG["cookie"] = "a=b"

        headers = build_headers()

        self.assertNotIn("Cookie", headers)

    def test_parse_cookie_header_skips_invalid_parts(self):
        self.assertEqual(
            parse_cookie_header("qrator_jsid2=abc; bad-part; region=moscow"),
            {"qrator_jsid2": "abc", "region": "moscow"},
        )

    async def test_fetch_with_retry_returns_text_on_success(self):
        session = SimpleNamespace(get=AsyncMock(return_value=FakeResponse(200, "x" * 250)))

        text = await fetch_with_retry(session, "https://lemanapro.ru/catalogue/test/", 5)

        self.assertEqual(text, "x" * 250)
        session.get.assert_awaited_once()

    async def test_fetch_with_retry_stops_on_401(self):
        session = SimpleNamespace(get=AsyncMock(return_value=FakeResponse(401, "denied")))
        CONFIG["max_retries"] = 3

        with patch("lemana_parser.http_utils.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            text = await fetch_with_retry(session, "https://lemanapro.ru/catalogue/test/", 5)

        self.assertIsNone(text)
        session.get.assert_awaited_once()
        sleep_mock.assert_not_awaited()

    async def test_fetch_with_retry_retries_retryable_status(self):
        session = SimpleNamespace(
            get=AsyncMock(side_effect=[FakeResponse(429, "busy"), FakeResponse(200, "y" * 250)])
        )
        CONFIG["max_retries"] = 2
        CONFIG["retry_backoff"] = 0.1

        with patch("lemana_parser.http_utils.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            text = await fetch_with_retry(session, "https://lemanapro.ru/catalogue/test/", 5)

        self.assertEqual(text, "y" * 250)
        self.assertEqual(session.get.await_count, 2)
        sleep_mock.assert_awaited_once()

    async def test_fetch_with_retry_result_reports_retryable_hits(self):
        session = SimpleNamespace(
            get=AsyncMock(side_effect=[FakeResponse(403, "blocked"), FakeResponse(200, "z" * 250)])
        )
        CONFIG["max_retries"] = 2
        CONFIG["retry_backoff"] = 0.1

        with patch("lemana_parser.http_utils.asyncio.sleep", new=AsyncMock()):
            result = await fetch_with_retry_result(session, "https://lemanapro.ru/product/test/", 5)

        self.assertEqual(result.html, "z" * 250)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.attempts, 2)
        self.assertEqual(result.retryable_hits, 1)

    async def test_fetch_with_retry_result_can_stop_on_antibot_status(self):
        session = SimpleNamespace(get=AsyncMock(return_value=FakeResponse(403, "blocked")))
        CONFIG["max_retries"] = 3

        with patch("lemana_parser.http_utils.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            result = await fetch_with_retry_result(
                session,
                "https://lemanapro.ru/product/test/",
                5,
                stop_on_status_codes={403},
            )

        self.assertIsNone(result.html)
        self.assertEqual(result.status_code, 403)
        self.assertEqual(result.attempts, 1)
        self.assertEqual(result.retryable_hits, 1)
        session.get.assert_awaited_once()
        sleep_mock.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
