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

Быстрый старт на новом Windows-компьютере:

```bat
git clone https://github.com/klimgaranin/lemana-parser.git
cd lemana-parser
setup_win.bat
copy .env.example .env
scripts\check_win.bat
run_win.bat --help
```

После этого вставь актуальную cookie в `.env` и запускай диагностику:

```bat
.venv\Scripts\python.exe main.py --check-cookie --no-pause
```

```bat
setup_win.bat
```

Скрипт создаёт `.venv`, устанавливает зависимости из `requirements.txt` и Chromium для Playwright. Проект можно хранить в Git, выгрузить на любой Windows-компьютер, запустить `setup_win.bat`, заполнить `.env` и работать через `run_win.bat`.

## Настройка

1. Скопируй `.env.example` в `.env`.
2. При необходимости измени `LEMANA_CATALOG_URL`, `LEMANA_OUTPUT_DIR`, `LEMANA_OUTPUT_FILENAME`.
3. Если `LEMANA_COOKIE` пустой или протух, парсер сам попробует обновить cookie через Chrome CDP.

## Запуск

```bat
run_win.bat
```

Параметры можно передавать без редактирования `.env`:

```bat
run_win.bat --url "https://lemanapro.ru/catalogue/..." --max-products 100 --product-concurrency 4
```

Полезные параметры:

- `--url` — URL первой страницы каталога.
- `--output-dir` и `--output-filename` — куда сохранить Excel.
- `--max-products` — ограничение количества товаров.
- `--catalog-concurrency` и `--product-concurrency` — верхняя параллельность запросов.
- `--product-batch-sleep` — пауза между батчами карточек.
- `--product-max-batch-sleep` — верхняя граница адаптивной паузы при `403/429`.
- `--product-max-active-batch` — реальный потолок размера батча карточек.
- `--product-min-recovery-sleep` — минимальная пауза после восстановления от `403/429`.
- `--product-pressure-cooldown` — длинная пауза после антибот-сигнала.
- `--product-deferred-rounds` и `--product-deferred-sleep` — медленные повторы отложенных карточек.
- `--browser-impersonate` — профиль `curl_cffi`, по умолчанию `chrome`.
- `--cookie` — cookie прямо из командной строки.
- `--no-playwright` — не открывать браузер, использовать cookie из `.env` или `--cookie`.
- `--check-cookie` — запустить диагностику cookie через `main.py`.
- `--debug` — подробные логи.
- `--no-pause` — не ждать Enter в конце.

## Диагностика cookie

PowerShell запускает `.bat` из текущей папки только с префиксом `.\`:

```powershell
.\get_cookie.bat
.venv\Scripts\python.exe check_cookie.py
.venv\Scripts\python.exe main.py --check-cookie --no-pause
```

`get_cookie.bat` открывает Chrome с debug-портом в локальном профиле `.chrome_cdp_profile/` и ждёт до 120 секунд. Если сайт показывает Qrator-проверку, пройди её в открытом окне Chrome и дождись сохранения cookie в `.env`.

Обычный запуск тоже проверяет cookie перед парсингом. Если каталог или первая карточка возвращают `401/403/429`, парсер автоматически пробует обновить cookie через Chrome CDP, сохраняет её в `.env` и проверяет повторно. CDP использует локальный профиль `.chrome_cdp_profile/`, чтобы не выглядеть как новый браузер при каждом запуске.

```env
LEMANA_COOKIE_PREFLIGHT=true
LEMANA_COOKIE_AUTO_REFRESH=true
```

Если автообновление не сработало, смотри причину в логе: Chrome не найден, CDP не поднялся, Qrator не выдал `qrator_jsid2` или новая cookie не прошла проверку.

## Скорость и антибот-ограничения

По умолчанию карточки товаров работают в стабильном режиме: активный батч не поднимается выше 2, а пауза после восстановления не опускается ниже 2 секунд. Если сервер отвечает `403/429`, парсер сбрасывается до `batch=1`, делает cooldown и только после нескольких стабильных батчей осторожно возвращается к `batch=2`:

```env
LEMANA_PRODUCT_CONCURRENCY=2
LEMANA_PRODUCT_BATCH_SLEEP=2.0
LEMANA_PRODUCT_MAX_BATCH_SLEEP=10.0
LEMANA_PRODUCT_ADAPTIVE_THROTTLE=true
LEMANA_PRODUCT_RECOVERY_BATCHES=6
LEMANA_PRODUCT_MAX_ACTIVE_BATCH=2
LEMANA_PRODUCT_MIN_RECOVERY_SLEEP=2.0
LEMANA_PRODUCT_DEFERRED_RETRY=true
LEMANA_PRODUCT_DEFERRED_ROUNDS=3
LEMANA_PRODUCT_DEFERRED_SLEEP=6.0
LEMANA_PRODUCT_PRESSURE_COOLDOWN=20.0
```

При `403/429` на карточке парсер не делает серию немедленных повторов по тому же URL. Карточка откладывается, затем проходит до 3 медленных одиночных раундов. Это медленнее, зато снижает количество пустых строк в Excel.

`LEMANA_PRODUCT_PRESSURE_COOLDOWN` задаёт паузу напрямую. Она не умножается на `LEMANA_PRODUCT_MIN_RECOVERY_SLEEP`, поэтому можно отдельно держать карточки медленными, а cooldown оставить 15-20 секунд:

```bat
run_win.bat --product-batch-sleep 3.5 --product-min-recovery-sleep 3.5 --product-pressure-cooldown 20
```

Если даже стабильный режим часто ловит `403`, запусти максимально бережно:

```bat
run_win.bat --no-playwright --product-concurrency 1 --product-max-active-batch 1 --product-batch-sleep 4 --product-deferred-sleep 10 --product-pressure-cooldown 30
```

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
