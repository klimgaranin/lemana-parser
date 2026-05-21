# LemanapPRO Parser

HTML-парсер каталога lemanapro.ru: получает cookie, собирает товары из каталога, догружает карточки и сохраняет результат в Excel.

## Структура проекта

Основной код находится в пакете `lemana_parser/`:

- `cli.py` — CLI и общий сценарий запуска;
- `config.py` — `.env`, CLI-переопределения и валидация;
- `catalog.py`, `products.py` — сбор каталога и карточек товаров;
- `parsers/html.py` — HTML-парсинг цен, картинок и характеристик;
- `http_utils.py` — HTTP-сессия, заголовки и retry;
- `excel_writer.py` — запись результата в Excel;
- `auth/` и `diagnostics/` — cookie и диагностика.

В корне оставлены короткие точки входа `main.py`, `check_cookie.py`, `cookie_grabber.py`, чтобы Windows-скрипты и ручной запуск оставались простыми. Служебные команды лежат в `scripts/`.

## Основной сценарий: Windows

```bat
setup_win.bat
```

Скрипт создаёт `.venv`, устанавливает зависимости из `requirements.txt` и Chromium для Playwright. Проект можно хранить в Git, выгрузить на любой Windows-компьютер, запустить `setup_win.bat`, заполнить `.env` и работать через `run_win.bat`.

## Настройка

1. Скопируй `.env.example` в `.env`.
2. При необходимости измени `LEMANA_CATALOG_URL`, `LEMANA_OUTPUT_DIR`, `LEMANA_OUTPUT_FILENAME`.
3. Если автоматическое получение cookie не сработало, заполни `LEMANA_COOKIE`.

## Запуск

```bat
run_win.bat
```

Параметры можно передавать без редактирования `.env`:

```bat
run_win.bat --url "https://lemanapro.ru/catalogue/..." --max-products 100 --product-concurrency 1
```

Полезные параметры:

- `--url` — URL первой страницы каталога.
- `--output-dir` и `--output-filename` — куда сохранить Excel.
- `--max-products` — ограничение количества товаров.
- `--catalog-concurrency` и `--product-concurrency` — параллельность запросов.
- `--product-batch-sleep` — пауза между батчами карточек.
- `--cookie` — cookie прямо из командной строки.
- `--no-playwright` — не открывать браузер, использовать cookie из `.env` или `--cookie`.
- `--check-cookie` — запустить диагностику cookie через `main.py`.
- `--debug` — подробные логи.
- `--no-pause` — не ждать Enter в конце.

## Диагностика cookie

```bat
get_cookie.bat
.venv\Scripts\python.exe check_cookie.py
.venv\Scripts\python.exe main.py --check-cookie --no-pause
```

Если сайт отдаёт `403`, значит нужна актуальная cookie. Скопируй заголовок `cookie` из браузера и вставь его в `.env` как `LEMANA_COOKIE`.

## Тесты

Для разработки установи дополнительные инструменты:

```bat
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Запускай тесты через виртуальное окружение проекта:

```bat
scripts\test_win.bat
```

Для WSL/Linux-разработки аналог:

```bash
scripts/test_dev.sh
```

Полная локальная проверка без боевого парсинга:

```bat
scripts\check_win.bat
```

Проверка и форматирование кода:

```bat
scripts\lint_win.bat
scripts\format_win.bat
```

Очистка локальных артефактов разработки:

```bat
scripts\clean_dev.bat
```

## Малый безопасный прогон

После успешной проверки cookie сначала запускай небольшую выборку:

```bat
.venv\Scripts\python.exe main.py --no-playwright --max-products 5 --catalog-concurrency 1 --product-concurrency 1 --product-batch-sleep 4 --no-pause
```
