"""
playwright_auth.py v5 — Cookie-first стратегия.

Приоритет:
  1. LEMANA_COOKIE в .env  →  использует напрямую (быстро, надёжно)
  2. Playwright             →  если .env пуст (работает только на RU IP)
  3. Инструкция             →  если всё остальное не помогло

Почему .env-подход лучший на не-RU IP:
  Qrator привязывает qrator_jsid2 к IP + browser fingerprint.
  Браузер пользователя (Chrome) уже имеет валидный qrator_jsid2
  для его IP. Скопировав его в .env, парсер делает запросы
  с того же IP → Qrator пропускает.
"""

import logging
import time
from contextlib import suppress

from playwright.sync_api import sync_playwright

logger = logging.getLogger("playwright_auth")

PAGE_TIMEOUT_MS = 35_000
MAX_WAIT_COOKIE_S = 20


def harvest_cookies_sync(url: str) -> str:
    from lemana_parser.config import CONFIG

    # ── 1. Используем cookie из .env если он есть ─────────────────────────
    existing = (CONFIG.get("cookie") or "").strip()
    if existing:
        has_q = "qrator_jsid2" in existing
        logger.info(
            "🍪 Используем cookie из .env (%d симв | qrator_jsid2=%s)",
            len(existing),
            "✓" if has_q else "⚠️ ОТСУТСТВУЕТ",
        )
        if not has_q:
            logger.warning(
                "⚠️  В .env нет qrator_jsid2 — возможны HTTP 401. "
                "Запусти cookie_grabber.py или смотри ИНСТРУКЦИЯ_COOKIE.txt"
            )
        return existing

    # ── 2. Playwright (только если .env пуст) ─────────────────────────────
    logger.info("🌐 .env пуст → пробуем Playwright (headless=False)...")
    logger.info("   Откроется окно браузера, закроется само")

    try:
        cookie_str = _playwright_harvest(url)
        if "qrator_jsid2" in cookie_str:
            logger.info("✅ Playwright получил qrator_jsid2!")
            return cookie_str
        logger.warning("⚠️  Playwright не получил qrator_jsid2")
    except Exception as e:
        logger.error("Playwright упал: %s", e)

    # ── 3. Fallback: инструкция ───────────────────────────────────────────
    _print_manual_help()
    raise RuntimeError(
        "Нет валидного cookie. Добавь LEMANA_COOKIE в .env (смотри ИНСТРУКЦИЯ_COOKIE.txt)"
    )


def _playwright_harvest(url: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            locale="ru-RU",
            timezone_id="Europe/Moscow",
        )
        context.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        page = context.new_page()
        with suppress(Exception):
            page.goto(url, wait_until="networkidle", timeout=PAGE_TIMEOUT_MS)

        for _ in range(MAX_WAIT_COOKIE_S):
            cookies = context.cookies()
            if any(c["name"] == "qrator_jsid2" for c in cookies):
                break
            time.sleep(1)
        else:
            cookies = context.cookies()

        browser.close()

    return "; ".join(f"{c['name']}={c['value']}" for c in cookies)


def _print_manual_help() -> None:
    print()
    print("=" * 55)
    print("  ⚠️  Нужна ручная вставка cookie")
    print("=" * 55)
    print("  1. Открой Chrome → lemanapro.ru/catalogue/")
    print("  2. F12 → Network → F5 → кликни первый запрос")
    print("  3. Request Headers → строка 'cookie:' → Copy value")
    print("  4. Открой .env в папке проекта")
    print('  5. LEMANA_COOKIE=\\"<вставь сюда>\\"')
    print("  6. Сохрани → запусти run_win.bat")
    print()
    print("  Или запусти: python cookie_grabber.py")
    print("=" * 55)
