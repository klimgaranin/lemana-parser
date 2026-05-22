import json
import os
import subprocess
import sys
import time
import urllib.request
from argparse import ArgumentParser
from contextlib import suppress
from pathlib import Path
from typing import Any

from lemana_parser.http_utils import CHROME_124_USER_AGENT

TARGET_HOST = "lemanapro.ru"
DEBUG_PORT = 9223
DEFAULT_URL = f"https://{TARGET_HOST}/catalogue/"
WAIT_AFTER_OPEN_SEC = 5
MAX_WAIT_COOKIE_SEC = 120
POLL_INTERVAL_SEC = 3
PROFILE_DIR = Path(".chrome_cdp_session")

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]


class CookieGrabberError(RuntimeError):
    """Ошибка автоматического получения cookie."""


def find_chrome() -> str:
    for p in CHROME_PATHS:
        if os.path.exists(p):
            return p
    return ""


def _urlopen_json(url: str, timeout: int = 3) -> Any:
    raw = urllib.request.urlopen(url, timeout=timeout).read()
    return json.loads(raw)


def _get_tabs() -> list[dict[str, Any]]:
    try:
        tabs = _urlopen_json(f"http://localhost:{DEBUG_PORT}/json/list")
    except Exception as exc:
        raise CookieGrabberError(f"не удалось подключиться к Chrome CDP: {exc}") from exc
    return tabs if isinstance(tabs, list) else []


def _pick_page_ws_url(tabs: list[dict[str, Any]]) -> str:
    for tab in tabs:
        if TARGET_HOST in tab.get("url", "") and tab.get("webSocketDebuggerUrl"):
            return tab["webSocketDebuggerUrl"]
    for tab in tabs:
        if tab.get("type") == "page" and tab.get("webSocketDebuggerUrl"):
            return tab["webSocketDebuggerUrl"]
    return ""


def _cdp_call(ws_url: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    import websocket

    ws = websocket.create_connection(ws_url, timeout=5)
    try:
        ws.send(json.dumps({"id": 1, "method": method, "params": params or {}}))
        while True:
            data = json.loads(ws.recv())
            if data.get("id") == 1:
                if "error" in data:
                    message = data["error"].get("message", data["error"])
                    raise CookieGrabberError(f"CDP {method}: {message}")
                return data.get("result", {})
    finally:
        ws.close()


def _get_browser_ws_url() -> str:
    try:
        version = _urlopen_json(f"http://localhost:{DEBUG_PORT}/json/version")
    except Exception:
        return ""
    return version.get("webSocketDebuggerUrl", "") if isinstance(version, dict) else ""


def _navigate_page(page_ws_url: str, url: str) -> None:
    try:
        _cdp_call(page_ws_url, "Page.navigate", {"url": url})
    except Exception as exc:
        print(f"⚠️  Не удалось открыть URL через CDP: {exc}")


def _collect_cookies(page_ws_url: str, url: str) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []

    browser_ws_url = _get_browser_ws_url()
    if browser_ws_url:
        with suppress(Exception):
            collected.extend(_cdp_call(browser_ws_url, "Storage.getCookies").get("cookies", []))

    for method, params in (
        ("Network.getCookies", {"urls": [url, f"https://{TARGET_HOST}/"]}),
        ("Network.getAllCookies", {}),
    ):
        with suppress(Exception):
            collected.extend(_cdp_call(page_ws_url, method, params).get("cookies", []))

    return collected


def _format_site_cookies(cookies: list[dict[str, Any]]) -> str:
    site_cookies = []
    seen: set[tuple[str, str, str]] = set()
    for cookie in cookies:
        domain = str(cookie.get("domain", ""))
        name = str(cookie.get("name", ""))
        value = str(cookie.get("value", ""))
        path = str(cookie.get("path", "/"))
        if not name or TARGET_HOST not in domain:
            continue
        key = (domain, path, name)
        if key in seen:
            continue
        seen.add(key)
        site_cookies.append(f"{name}={value}")

    return "; ".join(site_cookies)


def get_cookies_via_cdp(url: str) -> str:
    try:
        tabs = _get_tabs()
    except CookieGrabberError as exc:
        print(f"❌ {exc}")
        return ""

    page_ws_url = _pick_page_ws_url(tabs)
    if not page_ws_url:
        print("❌ Нет открытых вкладок Chrome")
        return ""

    _navigate_page(page_ws_url, url)
    cookies = _collect_cookies(page_ws_url, url)
    cookie_str = _format_site_cookies(cookies)
    if not cookie_str:
        print(f"⚠️  Нет cookie для {TARGET_HOST}")
    return cookie_str


def _is_cdp_ready() -> bool:
    try:
        _urlopen_json(f"http://localhost:{DEBUG_PORT}/json/version", timeout=1)
    except Exception:
        return False
    return True


def _start_chrome(chrome: str, url: str) -> subprocess.Popen | None:
    if _is_cdp_ready():
        print(f"ℹ️  Используем уже запущенный Chrome CDP на порту {DEBUG_PORT}")
        return None

    PROFILE_DIR.mkdir(exist_ok=True)
    return subprocess.Popen(
        [
            chrome,
            f"--remote-debugging-port={DEBUG_PORT}",
            f"--user-data-dir={PROFILE_DIR.resolve()}",
            "--remote-allow-origins=*",
            f"--user-agent={CHROME_124_USER_AGENT}",
            "--lang=ru-RU",
            "--no-first-run",
            "--disable-default-apps",
            "--new-window",
            url,
        ]
    )


def _save_cookie_to_env(cookie_str: str, env_path: str = ".env") -> None:
    path = Path(env_path)
    env_lines = []
    if path.exists():
        env_lines = [
            line
            for line in path.read_text(encoding="utf-8").splitlines(keepends=True)
            if not line.startswith("LEMANA_COOKIE")
        ]

    env_lines.append(f'LEMANA_COOKIE="{cookie_str}"\n')
    path.write_text("".join(env_lines), encoding="utf-8")


def _parse_args(argv: list[str] | None = None):
    parser = ArgumentParser(description="Получает cookie lemanapro.ru из Chrome через CDP.")
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help="Страница, которую открыть в Chrome перед чтением cookie.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    url = args.url

    print("=" * 55)
    print("  Cookie Grabber для lemanapro.ru")
    print("=" * 55)

    chrome = find_chrome()
    if not chrome:
        print("❌ Chrome не найден. Укажи путь вручную в CHROME_PATHS")
        sys.exit(1)

    print(f"✅ Chrome найден: {chrome}")
    print(f"🌐 Открываем {TARGET_HOST} с debug-портом {DEBUG_PORT}...")
    print("   Если откроется проверка Qrator — пройди её в окне Chrome.")

    proc = _start_chrome(chrome, url)
    print(f"⏳ Ждём {WAIT_AFTER_OPEN_SEC} сек после открытия браузера...")
    time.sleep(WAIT_AFTER_OPEN_SEC)

    cookie_str = ""
    deadline = time.monotonic() + MAX_WAIT_COOKIE_SEC
    attempt = 1
    while time.monotonic() < deadline:
        cookie_str = get_cookies_via_cdp(url)
        if "qrator_jsid2" in cookie_str:
            break
        left = max(0, int(deadline - time.monotonic()))
        print(f"  попытка {attempt}: qrator_jsid2 ещё не получен, ждём... осталось ~{left} сек")
        attempt += 1
        time.sleep(POLL_INTERVAL_SEC)

    if proc:
        proc.terminate()

    if not cookie_str:
        print("\n❌ Не удалось получить cookie автоматически.")
        print("   Сделай вручную (см. ИНСТРУКЦИЯ_COOKIE.txt)")
        return

    has_qrator = "qrator_jsid2" in cookie_str
    print("\n✅ Cookie получен!")
    print(f"   Символов: {len(cookie_str)}")
    print(f"   qrator_jsid2: {'✓' if has_qrator else '✗ ОТСУТСТВУЕТ'}")

    _save_cookie_to_env(cookie_str)

    print("\n✅ Сохранено в .env")
    print("   Теперь запускай: run_win.bat")

    if not has_qrator:
        print("\n⚠️  qrator_jsid2 отсутствует — смотри ИНСТРУКЦИЯ_COOKIE.txt")


if __name__ == "__main__":
    main()
    input("\nНажми Enter для выхода...")
