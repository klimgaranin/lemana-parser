"""
config.py — Настройки парсера LemanapPRO.
Меняй только CATALOG_URL и OUTPUT_FILENAME.
Cookie управляются Playwright автоматически — вручную вводить не нужно.
"""
import os
from dotenv import load_dotenv

load_dotenv()

CONFIG = {
    # ── Целевой каталог ──────────────────────────────────────────────────────
    # Просто вставь URL нужного раздела lemanapro.ru
    # Кириллицу в query-параметрах percent-encode сам или оставляй — код справится.
    "catalog_first_page_url": (
        "https://lemanapro.ru/catalogue/svetilniki-dlya-vannoy/"
        "?deliveryType=%D0%A1%D0%B0%D0%BC%D0%BE%D0%B2%D1%8B%D0%B2%D0%BE%D0%B7"
        "+%D0%B2+%D0%BC%D0%B0%D0%B3%D0%B0%D0%B7%D0%B8%D0%BD%D0%B5"
    ),

    # ── Вывод ────────────────────────────────────────────────────────────────
    "output_dir":      "output",
    "output_filename": "lemana_result.xlsx",

    # ── Ограничители ─────────────────────────────────────────────────────────
    "max_products":     100000,
    "max_pages_safety": 8000,

    # ── Параллелизм ──────────────────────────────────────────────────────────
    "catalog_concurrency": 8,
    "product_concurrency": 1,

    # ── Таймауты (секунды) ───────────────────────────────────────────────────
    "catalog_timeout": 25,
    "product_timeout": 30,

    # ── Повторы при ошибке ───────────────────────────────────────────────────
    "max_retries":   4,
    "retry_backoff": 0.6,

    # ── Адаптивная пауза между батчами (мс) ─────────────────────────────────
    "min_sleep_ms": 1500,
    "max_sleep_ms": 3500,

    # ── Cookie (Playwright заполняет автоматически) ──────────────────────────
    # Можно оставить пустым. Playwright обновит при старте.
    "cookie": os.getenv("LEMANA_COOKIE", "").strip().strip('"\''),
}

# Базовые колонки — всегда первые в xlsx
BASE_HEADERS = [
    "Артикул ЛМ",
    "ССЫЛКА",
    "Наименование товара",
    "Цена на сайте",
    "Ссылка на картинку",
]
