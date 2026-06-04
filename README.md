# LemanapPRO Parser

Парсер каталога lemanapro.ru: получает cookie, собирает товары из каталога или по списку артикулов ЛМ и сохраняет результат в Excel. Основной режим — `api-fallback`: сначала быстрый API сайта, при сбое переход на проверенный HTML-режим.

## Структура проекта

Основной код находится в пакете `lemana_parser/`:

- `cli.py` — CLI и общий сценарий запуска;
- `config.py` — `.env`, CLI-переопределения и валидация;
- `catalog.py`, `products.py` — сбор каталога и карточек товаров;
- `api/` — API-контекст, клиент внутренних методов сайта и нормализация API-ответов;
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
.\setup_win.bat
copy .env.example .env
.\scripts\check_win.bat
.\run_win.bat --help
```

После этого вставь актуальную cookie в `.env` и запускай диагностику:

```bat
.venv\Scripts\python.exe main.py --check-cookie --no-pause
```

```bat
.\setup_win.bat
```

Скрипт создаёт `.venv`, устанавливает зависимости из `requirements.txt` и Chromium для Playwright. Проект можно хранить в Git, выгрузить на любой Windows-компьютер, запустить `.\setup_win.bat`, заполнить `.env` и работать через `.\run_win.bat`.

## Настройка `.env`

1. Скопируй `.env.example` в `.env`.
2. При необходимости измени `LEMANA_CATALOG_URL`, `LEMANA_OUTPUT_DIR`, `LEMANA_OUTPUT_FILENAME`.
3. По умолчанию включён `LEMANA_DATA_SOURCE=api-fallback`. При необходимости можно выбрать `html` или `api`.
4. Если `LEMANA_COOKIE` пустой или протух, парсер сам попробует обновить cookie через Chrome CDP.

`.env.example` — это читаемый шаблон с комментариями по группам. Рабочие значения хранятся в `.env`, он не должен попадать в Git.

Минимум для первого запуска:

```env
LEMANA_CATALOG_URL="https://lemanapro.ru/catalogue/..."
LEMANA_DATA_SOURCE="api-fallback"
LEMANA_COOKIE=""
```

Если после `git pull` Git пишет, что локальный `.env.example` мешает обновлению, обычно это значит, что файл случайно правили на Windows. Если эти правки не нужны:

```powershell
git restore .env.example
git pull origin main
```

Настоящий `.env` при этом не трогается.

## Запуск

```bat
.\run_win.bat
```

Параметры можно передавать без редактирования `.env`:

```bat
.\run_win.bat --url "https://lemanapro.ru/catalogue/..." --max-products 100 --product-concurrency 4
```

Обычный запуск уже использует `api-fallback`. Явно указать режим можно так:

```bat
.\run_win.bat --data-source api-fallback --max-products 100
```

Выгрузка по списку артикулов ЛМ:

```bat
.\run_win.bat --articles "89363286, 89363281, 89413689"
.\run_win.bat --articles-file articles.txt
```

Для режима `--articles` парсер сначала запрашивает данные стандартным API-запросом, а если часть артикулов не вернулась, повторяет только недостающие товары без фасетов текущей категории и без `filterByEligibility`. Если API всё равно не отдаёт товар, строка остаётся в Excel со статусом `api_data_missing`.
Для A/B теста можно запустить список артикулов сразу в relaxed-режиме:

```bat
.\run_win.bat --articles-file articles.txt --api-articles-mode relaxed --api-page-size 100 --api-articles-sleep 3 --max-articles 100
```

Полезные параметры:

- `--url` — URL первой страницы каталога.
- `--output-dir` и `--output-filename` — куда сохранить Excel.
- `--max-products` — ограничение количества товаров.
- `--data-source html|api|api-fallback` — источник данных. `api-fallback` сначала пробует API, затем текущий HTML-режим.
- `--articles` и `--articles-file` — выгрузка по списку артикулов ЛМ через API.
- `--max-articles` — ограничение количества артикулов после чтения файла и удаления дублей.
- `--api-page-size` — размер API-батча.
- `--api-catalog-concurrency` — сколько API-страниц каталога грузить одновременно. `1` стабильно, `8+` speed-test.
- `--api-articles-sleep` — пауза между API-батчами в режиме списка артикулов.
- `--api-articles-mode strict-then-relaxed|relaxed` — обычный режим с повтором только недостающих товаров или прямой relaxed-запрос.
- `--api-transport local|gas|gas-fallback` — транспорт API для каталога и списка артикулов.
- `--gas-proxy-url` и `--gas-proxy-token` — URL и необязательный токен опубликованного GAS Web App.
- `--profile stable|careful|fast` — готовый профиль загрузки карточек.
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
- `--debug` — подробные логи в консоли. Файл `parser.log` всегда пишет больше технических деталей, чем экран.
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
LEMANA_SSL_VERIFY=true
```

Если автообновление не сработало, смотри причину в логе: Chrome не найден, CDP не поднялся, Qrator не выдал `qrator_jsid2` или новая cookie не прошла проверку.

## Безопасность и локальные файлы

`.env`, cookie, HAR-файлы, сохранённые HTML-снимки, логи и Excel-выгрузки не должны попадать в Git. Эти файлы уже добавлены в `.gitignore`, но после диагностики их лучше удалять из рабочей папки.

HTTPS-сертификаты проверяются по умолчанию:

```env
LEMANA_SSL_VERIFY=true
```

На Windows `curl_cffi` может не открыть `certifi\cacert.pem`, если проект лежит в папке с кириллицей. Парсер автоматически копирует CA bundle в ASCII-путь и использует его для HTTPS-проверки.

Отключать проверку через `LEMANA_SSL_VERIFY=false` стоит только как временную диагностику на проблемном компьютере, где явно сломано хранилище сертификатов.

## Скорость и антибот-ограничения

В основном `api-fallback` режиме каталог и данные товаров собираются пачками через API сайта. Боевые Windows-прогоны подтвердили: каталоги на 381 и 263 товара выгружаются за несколько секунд без загрузки каждой HTML-карточки.

HTML-режим остаётся резервным. Для него карточки товаров работают в стабильном режиме, подтверждённом боевыми прогонами: активный батч не поднимается выше 2, а пауза после восстановления не опускается ниже 4 секунд. Если сервер отвечает `403/429`, парсер сбрасывается до `batch=1`, делает cooldown и только после нескольких стабильных батчей осторожно возвращается к `batch=2`:

```env
LEMANA_PRODUCT_CONCURRENCY=2
LEMANA_PRODUCT_BATCH_SLEEP=4.0
LEMANA_PRODUCT_MAX_BATCH_SLEEP=10.0
LEMANA_PRODUCT_ADAPTIVE_THROTTLE=true
LEMANA_PRODUCT_RECOVERY_BATCHES=6
LEMANA_PRODUCT_MAX_ACTIVE_BATCH=2
LEMANA_PRODUCT_MIN_RECOVERY_SLEEP=4.0
LEMANA_PRODUCT_DEFERRED_RETRY=true
LEMANA_PRODUCT_DEFERRED_ROUNDS=3
LEMANA_PRODUCT_DEFERRED_SLEEP=6.0
LEMANA_PRODUCT_PRESSURE_COOLDOWN=15.0
```

При `403/429` на карточке парсер не делает серию немедленных повторов по тому же URL. Карточка откладывается, затем проходит до 3 медленных одиночных раундов. Это медленнее, зато снижает количество пустых строк в Excel.

`LEMANA_PRODUCT_PRESSURE_COOLDOWN` задаёт паузу напрямую. Она не умножается на `LEMANA_PRODUCT_MIN_RECOVERY_SLEEP`, поэтому можно отдельно держать карточки медленными, а cooldown оставить 15-20 секунд:

```bat
.\run_win.bat --product-batch-sleep 4 --product-min-recovery-sleep 4 --product-pressure-cooldown 15
```

Готовые профили:

```bat
.\run_win.bat --profile stable
.\run_win.bat --profile careful
.\run_win.bat --profile fast --max-products 30
```

- `stable` — основной боевой режим: `batch<=2`, пауза 4 сек, cooldown 15 сек.
- `careful` — максимально бережный режим: одиночные карточки, пауза 5 сек, cooldown 20 сек.
- `fast` — только для коротких тестов: быстрее, но риск `403` выше.

Если даже стабильный режим часто ловит `403`, запусти максимально бережно:

```bat
.\run_win.bat --profile careful
```

## API-режим

API-режим использует те же cookie и тот же preflight, что HTML-режим. Перед API-запросами парсер один раз загружает первую страницу каталога, вытаскивает из неё API-настройки сайта, затем получает товары пачками через:

- `products:search` — список артикулов товаров;
- `products-data:search` — названия, цены, ссылки и характеристики;
- `products-media:search` — изображения.

Это резко уменьшает количество запросов к сайту: вместо отдельной HTML-загрузки каждой карточки используются пачки до 60 товаров. `api-fallback` является основным режимом: при проблеме API парсер автоматически вернётся к HTML-сценарию.

## GAS proxy transport

GAS proxy — экспериментальный транспорт для API-запросов. Простыми словами:

- Python на компьютере запускает процесс, проверяет cookie, готовит Excel и управляет логикой.
- Google Apps Script делает API-запросы к Lemana PRO.
- Если Google IP реально реже ловит `403`, этот режим станет основным.

Режимы:

- `local` — API-запросы идут с компьютера пользователя.
- `gas` — API-запросы идут через Google Apps Script. Если GAS получает ошибку, запуск останавливается.
- `gas-fallback` — сначала GAS, а если batch/страница не прошли, парсер добирает их локальным API.

В консоли GAS-режим показывает короткие строки: метод, HTTP-статус, время ответа и маленький preview. Большие JSON-ответы не печатаются на экран, чтобы не забивать PowerShell. Подробные технические preview пишутся в `parser.log`.

URL для `LEMANA_GAS_PROXY_URL` берётся в Apps Script:

1. Открой проект Apps Script.
2. Нажми `Deploy` -> `Manage deployments`.
3. Создай или отредактируй deployment типа `Web app`.
4. `Execute as`: `Me`.
5. `Who has access`: для теста `Anyone` или `Anyone with Google account`.
6. Нажми `Deploy`.
7. Скопируй `Web app URL`, он должен заканчиваться на `/exec`.

Добавь в `.env`:

```env
LEMANA_API_TRANSPORT="gas-fallback"
LEMANA_GAS_PROXY_URL="https://script.google.com/macros/s/...../exec"
LEMANA_GAS_PROXY_TOKEN=""
LEMANA_API_FALLBACK_REGION_IDS=""
```

Если в Apps Script в `Script Properties` задан `LEMANA_PROXY_TOKEN`, такой же токен нужно указать в `LEMANA_GAS_PROXY_TOKEN`. Если token property не задан, оставь пусто.

`LEMANA_API_FALLBACK_REGION_IDS` — это резервные регионы для добора `api_data_missing`. Например:

```env
LEMANA_API_FALLBACK_REGION_IDS="35,36"
```

Это значит: если основной регион не вернул данные товара, GAS попробует эти `regionId`. Пока список регионов нужно заполнять только проверенными ID. Без проверенных ID оставь пусто.

После обновления GAS-кода через `clasp push` существующий Web App deployment может продолжить исполнять старую версию. В Apps Script сделай:

```text
Deploy -> Manage deployments -> Edit -> New version -> Deploy
```

### Артикулы через GAS

Контрольный локальный запуск:

```bat
.\run_win.bat --articles-file articles.txt --api-transport local --api-page-size 30 --api-articles-sleep 0 --max-articles 50
```

Что делает: берёт первые 50 артикулов из `articles.txt`, всё запрашивает с компьютера. Это база для сравнения.

Чистый GAS-тест:

```bat
.\run_win.bat --articles-file articles.txt --api-transport gas --api-page-size 30 --api-articles-sleep 0 --max-articles 50
```

Что делает: Python управляет запуском, но API-запросы товаров делает GAS. Если GAS словит `403/401/429`, запуск остановится, чтобы проблему было видно.

Безопасный GAS-запуск:

```bat
.\run_win.bat --articles-file articles.txt --api-transport gas-fallback --api-page-size 30 --api-articles-sleep 0 --max-articles 1000
```

Что делает: сначала пробует GAS, а если GAS batch сломался, добирает его локально. Это лучший режим для длинных боевых тестов.

### Каталог через GAS

Малый тест каталога:

```bat
.\run_win.bat --data-source api --api-transport gas --api-page-size 100 --max-products 300
```

Что делает: берёт каталог из `LEMANA_CATALOG_URL`, API-страницы каталога и данные товаров запрашивает через GAS, ограничивает выгрузку 300 товарами.

Ускоренный тест каталога после проверки стабильности:

```bat
.\run_win.bat --data-source api --api-transport gas --api-page-size 90 --api-catalog-concurrency 2
```

Что делает: оставляет безопасный размер batch `90`, но грузит 2 страницы каталога одновременно. Если в `API HTTP` появятся `403/409/429`, верни `--api-catalog-concurrency 1`.

Максимально быстрый тест каталога:

```bat
.\run_win.bat --data-source api --api-transport gas --api-page-size 90 --api-catalog-concurrency 16 --max-products 5000
```

Что делает: размер batch оставляет `90`, потому что выше уже ловится `409`, но агрессивно увеличивает количество одновременно загружаемых страниц. Если всё чисто, можно пробовать `--api-catalog-concurrency 24` или `32`. Если появляются `403/409/429`, уменьши concurrency.

Полный каталог через GAS:

```bat
.\run_win.bat --data-source api --api-transport gas --api-page-size 100
```

Что делает: выгружает весь каталог через GAS. Если GAS сломался, запуск остановится.

Полный каталог через GAS с подстраховкой:

```bat
.\run_win.bat --data-source api-fallback --api-transport gas-fallback --api-page-size 100
```

Что делает: сначала пробует каталог через GAS, а если GAS/API сломались, переходит в резервный сценарий.

### Как читать итог

В конце API/GAS-запуска есть строка:

```text
API HTTP : статусы 200=448, 403=0, 429=0; ошибки нет
```

Как понимать:

- `200` — нормальные запросы.
- `401` — проблема доступа, cookie или публикации GAS Web App.
- `403` — блокировка/антибот.
- `429` — слишком часто, нужно снижать batch или добавлять паузу.
- `5xx` — серверная ошибка.

Если видишь много `401/403/429`, запуск подозрительный.

### Что такое api_data_missing

`api_data_missing` — это не падение запроса. Это значит:

1. Артикул был во входном списке или найден в каталоге.
2. API-запрос прошёл.
3. Но `products-data:search` не вернул название/цену/ссылку товара.

В GAS-режиме такие товары остаются в GAS: после основного запроса парсер просит GAS добрать missing-товары через резервные `regionId` из:

```env
LEMANA_API_FALLBACK_REGION_IDS=""
```

Если список пустой, региональный добор не выполняется. Следующий этап — найти API-метод сайта, который отдаёт список регионов, и задокументировать его.

## Тесты

Для разработки установи дополнительные инструменты:

```bat
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Запускай тесты через виртуальное окружение проекта:

```bat
.\scripts\test_win.bat
```

Для WSL/Linux-разработки аналог:

```bash
scripts/test_dev.sh
```

Полная локальная проверка без боевого парсинга:

```bat
.\scripts\check_win.bat
```

Проверка и форматирование кода:

```bat
.\scripts\lint_win.bat
.\scripts\format_win.bat
```

Очистка локальных артефактов разработки:

```bat
.\scripts\clean_dev.bat
```

## Малый безопасный прогон

После успешной проверки cookie можно запустить небольшую API-выборку:

```bat
.venv\Scripts\python.exe main.py --no-playwright --data-source api-fallback --max-products 5 --no-pause
```
