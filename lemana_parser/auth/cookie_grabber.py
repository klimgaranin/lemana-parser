"""
cookie_grabber.py — Извлекает cookie lemanapro.ru из Chrome через CDP.

Запускай когда нужно обновить cookie (раз в 3-7 дней).
Chrome должен быть установлен на компьютере.
"""

import json
import os
import subprocess
import sys
import time

TARGET_HOST = "lemanapro.ru"
DEBUG_PORT = 9223
WAIT_SEC = 12  # ждём пока Qrator challenge решится

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]


def find_chrome() -> str:
    for p in CHROME_PATHS:
        if os.path.exists(p):
            return p
    return ""


def get_cookies_via_cdp(url: str) -> str:
    try:
        import urllib.request

        raw = urllib.request.urlopen(f"http://localhost:{DEBUG_PORT}/json/list", timeout=3).read()
        tabs = json.loads(raw)
    except Exception as e:
        print(f"❌ Не удалось подключиться к Chrome CDP: {e}")
        return ""

    ws_url = None
    for tab in tabs:
        if TARGET_HOST in tab.get("url", ""):
            ws_url = tab.get("webSocketDebuggerUrl")
            break
    if not ws_url and tabs:
        ws_url = tabs[0].get("webSocketDebuggerUrl")

    if not ws_url:
        print("❌ Нет открытых вкладок Chrome")
        return ""

    import threading

    import websocket  # pip install websocket-client

    result = {}

    def on_message(ws, message: str) -> None:
        data = json.loads(message)
        if "result" in data and "cookies" in data.get("result", {}):
            result["cookies"] = data["result"]["cookies"]
            ws.close()

    def on_open(ws) -> None:
        ws.send(json.dumps({"id": 1, "method": "Network.getAllCookies"}))

    ws = websocket.WebSocketApp(ws_url, on_message=on_message, on_open=on_open)
    t = threading.Thread(target=ws.run_forever)
    t.daemon = True
    t.start()
    t.join(timeout=5)

    cookies = result.get("cookies", [])
    site_cookies = [c for c in cookies if TARGET_HOST in c.get("domain", "")]
    if not site_cookies:
        print(f"⚠️  Нет cookie для {TARGET_HOST}")
        return ""

    return "; ".join(f"{c['name']}={c['value']}" for c in site_cookies)


def main() -> None:
    print("=" * 55)
    print("  Cookie Grabber для lemanapro.ru")
    print("=" * 55)

    chrome = find_chrome()
    if not chrome:
        print("❌ Chrome не найден. Укажи путь вручную в CHROME_PATHS")
        sys.exit(1)

    print(f"✅ Chrome найден: {chrome}")
    print(f"🌐 Открываем {TARGET_HOST} с debug-портом {DEBUG_PORT}...")

    proc = subprocess.Popen(
        [
            chrome,
            f"--remote-debugging-port={DEBUG_PORT}",
            "--user-data-dir=chrome_cdp_session",
            "--no-first-run",
            "--disable-default-apps",
            f"https://{TARGET_HOST}/",
        ]
    )

    print(f"⏳ Ждём {WAIT_SEC} сек (Qrator JS-challenge)...")
    time.sleep(WAIT_SEC)

    # Пробуем несколько раз
    cookie_str = ""
    for attempt in range(5):
        cookie_str = get_cookies_via_cdp(f"https://{TARGET_HOST}/")
        if "qrator_jsid2" in cookie_str:
            break
        print(f"  попытка {attempt + 1}: qrator_jsid2 ещё не получен, ждём...")
        time.sleep(3)

    proc.terminate()

    if not cookie_str:
        print("\n❌ Не удалось получить cookie автоматически.")
        print("   Сделай вручную (см. ИНСТРУКЦИЯ_COOKIE.txt)")
        return

    has_qrator = "qrator_jsid2" in cookie_str
    print("\n✅ Cookie получен!")
    print(f"   Символов: {len(cookie_str)}")
    print(f"   qrator_jsid2: {'✓' if has_qrator else '✗ ОТСУТСТВУЕТ'}")

    # Сохраняем в .env
    env_path = ".env"
    env_lines = []
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            env_lines = [line for line in f.readlines() if not line.startswith("LEMANA_COOKIE")]

    env_lines.append(f'LEMANA_COOKIE="{cookie_str}"\n')
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(env_lines)

    print("\n✅ Сохранено в .env")
    print("   Теперь запускай: run_win.bat")

    if not has_qrator:
        print("\n⚠️  qrator_jsid2 отсутствует — смотри ИНСТРУКЦИЯ_COOKIE.txt")


if __name__ == "__main__":
    main()
    input("\nНажми Enter для выхода...")
