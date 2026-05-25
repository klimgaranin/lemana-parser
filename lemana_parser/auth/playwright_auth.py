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

from lemana_parser.auth.cookie_grabber import CookieGrabberError, harvest_cookie_via_cdp
from lemana_parser.auth.cookie_health import check_cookie_sync

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
                "Пробуем автоматическое обновление."
            )

        if not CONFIG["cookie_preflight"]:
            return existing

        check = check_cookie_sync(url, existing)
        if check.ok:
            logger.info(
                "✅ Cookie проверена: каталог=%s, карточка=%s, карточек на странице=%d",
                check.catalog_status,
                check.product_status,
                check.catalog_cards,
            )
            return existing

        logger.warning("⚠️  Cookie из .env не прошла проверку: %s", check.reason)
        if not CONFIG["cookie_auto_refresh"]:
            raise RuntimeError(f"Cookie из .env не прошла проверку: {check.reason}")

    if CONFIG["cookie_auto_refresh"]:
        refreshed = _harvest_cdp_then_validate(url)
        if refreshed:
            return refreshed

    # ── 2. Playwright fallback ────────────────────────────────────────────
    logger.info("🌐 Пробуем Playwright (headless=False)...")
    logger.info("   Откроется окно браузера, закроется само")

    try:
        cookie_str = _playwright_harvest(url)
        check = check_cookie_sync(url, cookie_str)
        if "qrator_jsid2" in cookie_str and check.ok:
            logger.info("✅ Playwright получил и проверил qrator_jsid2!")
            return cookie_str
        logger.warning("⚠️  Playwright cookie не прошла проверку: %s", check.reason)
    except Exception as e:
        logger.error("Playwright упал: %s", e)

    # ── 3. Fallback: инструкция ───────────────────────────────────────────
    _print_manual_help()
    raise RuntimeError(
        "Нет валидного cookie. Добавь LEMANA_COOKIE в .env (смотри ИНСТРУКЦИЯ_COOKIE.txt)"
    )


def _harvest_cdp_then_validate(url: str) -> str:
    logger.info("🔁 Пробуем автоматически обновить cookie через Chrome CDP...")
    try:
        cookie_str = harvest_cookie_via_cdp(url, save=True)
    except CookieGrabberError as exc:
        logger.warning("⚠️  CDP cookie refresh не сработал: %s", exc)
        return ""

    check = check_cookie_sync(url, cookie_str)
    if check.ok:
        logger.info(
            "✅ CDP cookie обновлена и проверена: каталог=%s, карточка=%s",
            check.catalog_status,
            check.product_status,
        )
        return cookie_str

    logger.warning("⚠️  CDP cookie получена, но не прошла проверку: %s", check.reason)
    return ""


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
    print("  ⚠️  Автоматическое обновление cookie не удалось")
    print("=" * 55)
    print(r"  1. Запусти .\get_cookie.bat и дождись сохранения cookie")
    print(r"  2. Проверь: .venv\Scripts\python.exe main.py --check-cookie --no-pause")
    print(r"  3. Запусти .\run_win.bat --no-playwright")
    print()
    print("  Если Qrator показал проверку в Chrome, пройди её в открытом окне.")
    print("=" * 55)
