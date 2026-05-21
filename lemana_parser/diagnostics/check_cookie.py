"""Cookie and connection diagnostics for lemanapro.ru."""

import argparse
import os
import re

from lemana_parser.config import CONFIG, ConfigError, validate_config
from lemana_parser.http_utils import build_headers, describe_cookie


IMPORTANT_COOKIE_KEYS = [
    "qrator_jsid2",
    "qrator_jsr",
    "session",
    "auth",
    "token",
    "PHPSESSID",
    "ssid",
]


def _read_raw_cookie_from_env(env_path: str = ".env") -> str:
    if not os.path.exists(env_path):
        return ""

    with open(env_path, "r", encoding="utf-8") as file:
        for line in file:
            line_stripped = line.rstrip("\n")
            if not line_stripped.startswith("LEMANA_COOKIE"):
                continue

            _, _, value = line_stripped.partition("=")
            value = value.strip()
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            return value

    return ""


def _print_env_diagnostics(raw_cookie: str, dotenv_cookie: str) -> None:
    print("=" * 60)
    print("ШАГ 1: Чтение .env")
    print("=" * 60)

    if not raw_cookie:
        print("⚠️  LEMANA_COOKIE не найден в .env или пустой")
        print("   Парсер попробует получить cookie через Playwright при обычном запуске.")
        return

    print("Сырая cookie из .env: <скрыто>")
    print(f"Длина до dotenv:      {len(raw_cookie)}")
    print(f"Длина через dotenv:   {len(dotenv_cookie)}")

    if len(raw_cookie) != len(dotenv_cookie):
        print("\n⚠️  dotenv прочитал cookie другой длины")
        print("   Частая причина: символ # без двойных кавычек в .env.")
        print('   FIX: LEMANA_COOKIE="...полная строка cookie..."')
    else:
        print("✅ dotenv прочитал cookie без изменения длины")


def _print_cookie_parts(cookie: str) -> None:
    print("\n" + "=" * 60)
    print("ШАГ 2: Состав cookie")
    print("=" * 60)
    print(f"Итоговая cookie: {describe_cookie(cookie)}")

    parts = [part.strip() for part in cookie.split(";") if "=" in part]
    print(f"Всего фрагментов cookie: {len(parts)}")

    for key in IMPORTANT_COOKIE_KEYS:
        found = [part for part in parts if part.lower().startswith(key.lower())]
        status = "✅" if found else "❌"
        preview = "найден" if found else "НЕ найден"
        print(f"  {status} {key}: {preview}")


def _print_response_diagnostics(url: str, cookie: str) -> None:
    print("\n" + "=" * 60)
    print("ШАГ 3: Тестовый HTTP-запрос")
    print("=" * 60)

    try:
        from curl_cffi.requests import Session as CurlSession
    except ImportError:
        print("❌ curl_cffi не установлен. Запусти: pip install -r requirements.txt")
        return

    headers = build_headers(cookie=cookie)

    print(f"URL: {url}")
    print(f"Cookie: {describe_cookie(cookie)}")

    try:
        with CurlSession(impersonate="chrome124", verify=False) as session:
            resp = session.get(url, headers=headers, timeout=20, allow_redirects=True)
    except Exception as exc:
        print(f"❌ Ошибка запроса: {type(exc).__name__}: {exc}")
        return

    html = resp.text or ""
    cards = re.findall(r'data-product-id=["\']([^"\']+)["\']', html)
    has_next_data = bool(re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\']', html))
    has_products_list = bool(re.search(r'data-qa=["\']products-list["\']', html))

    print(f"\nHTTP статус:    {resp.status_code}")
    print(f"Итоговый URL:   {getattr(resp, 'url', '')}")
    print(f"Размер ответа:  {len(html)} символов")
    print(f"__NEXT_DATA__:  {'✅ найден' if has_next_data else '❌ НЕ найден'}")
    print(f"products-list:  {'✅ найден' if has_products_list else '❌ НЕ найден'}")
    print(f"Карточек:       {len(cards)}")

    if resp.status_code == 401:
        print("\n⚠️  401: cookie отклонена сервером.")
        print("   Обнови LEMANA_COOKIE через get_cookie.bat или инструкцию.")
    elif resp.status_code in {403, 429}:
        print("\n⚠️  403/429: сервер ограничивает запросы или считает сессию подозрительной.")
        print("   Уменьши concurrency, увеличь паузы или обнови cookie.")
    elif resp.status_code == 200 and not cards:
        print("\n⚠️  200, но карточек нет: изменилась HTML-разметка или вернулся SPA-shell.")
    elif resp.status_code == 200:
        print(f"\n✅ HTTP и cookie выглядят рабочими. Карточек на странице: {len(cards)}")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Проверяет .env cookie и доступность каталога lemanapro.ru.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _parse_args(argv)

    try:
        validate_config()
    except ConfigError as exc:
        print(f"❌ Ошибка конфигурации: {exc}")
        return 1

    raw_cookie = _read_raw_cookie_from_env()
    dotenv_cookie = CONFIG["cookie"]

    _print_env_diagnostics(raw_cookie, dotenv_cookie)
    _print_cookie_parts(dotenv_cookie)
    _print_response_diagnostics(CONFIG["catalog_first_page_url"], dotenv_cookie)

    print("\n" + "=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
