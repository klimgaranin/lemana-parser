"""
check_cookie.py — диагностика cookie и соединения с lemanapro.ru

Запуск:
    python check_cookie.py

Покажет:
  1. Что именно читается из .env (длина, есть ли qrator_jsid2, обрезана ли '#')
  2. HTTP-статус реального запроса к lemanapro.ru
  3. Есть ли __NEXT_DATA__ и товары в ответе
"""

import os
import re
import sys

# ─── 1. Читаем .env вручную (без dotenv) чтобы увидеть сырое значение ────────
print("=" * 60)
print("ШАГ 1: Чтение .env вручную (без python-dotenv)")
print("=" * 60)

raw_cookie_from_env = None
dotenv_cookie = None

# Читаем сырой файл
env_path = ".env"
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line_stripped = line.rstrip("\n")
            if line_stripped.startswith("LEMANA_COOKIE"):
                raw_cookie_from_env = line_stripped
                break

if raw_cookie_from_env:
    print(f"Сырая строка в .env:\n  {raw_cookie_from_env[:120]}...")
    # Извлекаем значение после '='
    _, _, val = raw_cookie_from_env.partition("=")
    val = val.strip()
    # Убираем кавычки как делает dotenv
    if (val.startswith('"') and val.endswith('"')) or \
       (val.startswith("'") and val.endswith("'")):
        val = val[1:-1]
    raw_cookie_from_env = val
    print(f"Длина (сырой, до dotenv): {len(raw_cookie_from_env)}")
else:
    print("❌ LEMANA_COOKIE не найдена в .env!")
    sys.exit(1)

# Читаем через dotenv (как делает config.py)
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
    dotenv_cookie = os.getenv("LEMANA_COOKIE", "").strip().strip("\"'")
    print(f"\nДлина (через dotenv): {len(dotenv_cookie)}")

    if len(raw_cookie_from_env) != len(dotenv_cookie):
        print(f"\n⚠️  ВНИМАНИЕ: dotenv ОБРЕЗАЛ cookie!")
        print(f"   Было:  {len(raw_cookie_from_env)} символов")
        print(f"   Стало: {len(dotenv_cookie)} символов")
        print(f"   Причина: скорее всего '#' в значении cookie (dotenv воспринимает как комментарий)")
        print(f"\n   FIX: оберни значение в .env в двойные кавычки:")
        print(f'   LEMANA_COOKIE="...полная строка с куками..."')
    else:
        print("✅ dotenv прочитал cookie без обрезки")
except ImportError:
    dotenv_cookie = raw_cookie_from_env
    print("(python-dotenv не установлен, используем сырое значение)")

cookie = dotenv_cookie or raw_cookie_from_env

# ─── 2. Анализ состава cookie ─────────────────────────────────────────────────
print("\n" + "=" * 60)
print("ШАГ 2: Состав cookie")
print("=" * 60)

important = ["qrator_jsid2", "qrator_jsr", "session", "auth", "token", "PHPSESSID", "ssid"]
parts = [p.strip() for p in cookie.split(";") if "=" in p]
print(f"Всего фрагментов cookie: {len(parts)}")
for key in important:
    found = [p for p in parts if p.lower().startswith(key.lower())]
    status = "✅" if found else "❌"
    print(f"  {status} {key}: {'найден (' + found[0][:50] + ')' if found else 'НЕ найден'}")

# ─── 3. Реальный HTTP-запрос ──────────────────────────────────────────────────
print("\n" + "=" * 60)
print("ШАГ 3: Тестовый HTTP-запрос к lemanapro.ru")
print("=" * 60)

url = "https://lemanapro.ru/catalogue/svetilniki-dlya-vannoy/"

try:
    from curl_cffi.requests import Session as CurlSession

    headers = {
        # НЕ ставим Cache-Control/Pragma — это подозрительно для "браузера"
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cookie": cookie,
    }

    print(f"URL: {url}")
    print(f"Cookie (первые 100 символов): {cookie[:100]}...")

    with CurlSession(impersonate="chrome124", verify=False) as s:
        resp = s.get(url, headers=headers, timeout=20, allow_redirects=True)

    print(f"\nHTTP статус:    {resp.status_code}")
    print(f"Размер ответа:  {len(resp.text)} символов")

    html = resp.text

    # Проверяем __NEXT_DATA__
    nd_match = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\']', html)
    print(f"__NEXT_DATA__:  {'✅ найден' if nd_match else '❌ НЕ найден'}")

    # Проверяем products-list
    pl_match = re.search(r'data-qa=["\']products-list["\']', html)
    print(f"products-list:  {'✅ найден' if pl_match else '❌ НЕ найден'}")

    # Считаем карточки
    cards = re.findall(r'data-product-id=["\']([^"\']+)["\']', html)
    print(f"Карточек:       {len(cards)}")

    if resp.status_code == 401:
        print("\n⚠️  401 — возможные причины:")
        print("   А) Cookie обрезана '#' → см. ШАГ 1")
        print("   Б) Qrator привязал cookie к IP браузера, а не к твоему текущему IP")
        print("   В) Сайт требует дополнительный заголовок (X-Requested-With и т.п.)")
        print("   Г) Cookie корректна, но Qrator видит подозрительные заголовки")
        print("      (Cache-Control: no-cache от парсера = красный флаг для бота-детектора)")

    if resp.status_code == 200 and not cards:
        print("\n⚠️  200 но товаров нет — скорее всего вернулся SPA-шелл без SSR")
        print("   Решение: переход на API-запросы (задача 2)")

    if resp.status_code == 200 and cards:
        print(f"\n✅ Всё работает! {len(cards)} карточек на странице")

except ImportError:
    print("❌ curl_cffi не установлен. Запусти: pip install curl_cffi")
except Exception as e:
    print(f"❌ Ошибка запроса: {e}")

print("\n" + "=" * 60)
