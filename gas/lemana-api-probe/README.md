# Lemana API Probe для Google Apps Script

Экспериментальный клиент внутренних API LemanaPRO для Google Sheets.

## Что умеет

- Создаёт листы:
  - `Settings` — настройки.
  - `Articles` — входной список артикулов ЛМ.
  - `Catalog Results` — результат сценария каталога.
  - `Article Results` — результат сценария артикулов.
  - `Debug Logs` — полный технический лог запросов и ответов.
- Сценарий каталога:
  - берёт `catalogUrl` из `Settings`;
  - читает HTML страницы;
  - достаёт `apiKey`, `apiBaseUrl`, `familyId`, `facets`;
  - вызывает `products:search`, `products-data:search`, `products-media:search`;
  - пишет товары в `Catalog Results`.
- Сценарий артикулов:
  - берёт артикулы из колонки `A` листа `Articles`;
  - вызывает `products-data:search` пачками;
  - при режиме `strict-then-relaxed` повторяет недостающие товары без фасетов и `filterByEligibility`;
  - при режиме `relaxed` сразу делает запрос без фасетов и `filterByEligibility`;
  - пишет товары в `Article Results`.

## Настройки

Основные ключи на листе `Settings`:

- `catalogUrl` — ссылка на каталог.
- `apiPageSize` — batch для каталога.
- `articlesBatchSize` — batch для артикулов.
- `articlesSleepMs` — пауза между batch артикулов.
- `articlesMode` — `strict-then-relaxed` или `relaxed`.
- `maxCatalogProducts` — лимит товаров каталога.
- `maxArticles` — лимит артикулов. `0` значит без лимита.
- `cookie` — необязательно. Можно вставить cookie, если HTML каталога блокируется.
- `logResponseBodyLimit` — сколько символов body писать в `Debug Logs`. Максимум 45000 из-за лимита ячейки Sheets.

## Ручная установка в Google Sheets

1. Создай Google Таблицу.
2. Открой `Расширения` -> `Apps Script`.
3. Удали стандартный код.
4. Создай/оставь файл `Code.gs` и вставь туда содержимое `Code.gs` из этой папки.
5. В настройках проекта Apps Script включи показ файла манифеста, если он скрыт.
6. Открой `appsscript.json` и замени содержимое на файл `appsscript.json` из этой папки.
7. Сохрани проект.
8. Вернись в таблицу и обнови страницу.
9. В меню появится `Lemana API`.
10. Нажми `Lemana API` -> `1. Создать/обновить листы`.
11. Заполни `Settings` и `Articles`.
12. Запусти `2. Запустить каталог` или `3. Запустить артикулы`.

При первом запуске Google попросит авторизацию. Нужно разрешить доступ к текущей таблице и внешним запросам.

## Установка через clasp по scriptId

Это более взрослый способ, если хочешь хранить GAS-код в Git и грузить его в Apps Script командой.

1. Установи Node.js.
2. Установи clasp:

```powershell
npm install -g @google/clasp
```

3. Авторизуйся:

```powershell
clasp login
```

4. В Apps Script открой проект, зайди в `Project Settings` и скопируй `Script ID`.
5. В папке `gas\lemana-api-probe` создай файл `.clasp.json`:

```json
{
  "scriptId": "ВСТАВЬ_СЮДА_SCRIPT_ID",
  "rootDir": "."
}
```

6. Из папки проекта на Windows выполни:

```powershell
cd gas\lemana-api-probe
clasp push
```

7. Вернись в таблицу, обнови страницу и запускай меню `Lemana API`.

## Как код экономит лимиты Sheets

- Настройки читаются одним диапазоном.
- Артикулы читаются одним диапазоном из колонки `A`.
- Результаты пишутся одним `setValues`.
- Debug-логи накапливаются в массиве в памяти и пишутся пачкой.
- Нет записи строк по одной.

## Важное

Это экспериментальный стенд. Он нужен, чтобы проверить, как API LemanaPRO реагирует на запросы с инфраструктуры Google.
Если QRATOR всё равно вернёт HTML `Access Blocked`, полный ответ будет в `Debug Logs`.
