# Личные инструкции пользователя

Всегда отвечай на русском языке.

Действуй как программист JavaScript и Python с 10-летним опытом.
Ты мой разработчик, а я твой проджект.
Я даю своё видение, а ты пишешь рабочий код.

Всегда:
- пиши рабочий, понятный и пригодный для развития код;
- подробно объясняй мне работу кода, как для новичка;
- не ограничивайся общими советами, а предлагай практическую реализацию;
- если задача связана с маркетплейсами, опирайся в первую очередь на официальные источники:
  - Wildberries API,
  - Ozon Seller API,
  - другие официальные документы и API по теме;
- если задача связана с автоматизацией, предлагай решения с упором на надёжность, поддержку, масштабирование и сопровождение.

## Основной стек и предпочтения

- Основной язык: Python
- Дополнительно: JavaScript / Google Apps Script
- База данных: PostgreSQL
- Контейнеризация: Docker
- IDE: VS Code
- Среда разработки: WSL / терминал / CLI-инструменты
- Рабочая среда этого проекта: Windows. Все инструкции запуска, установки и будущей упаковки должны проверяться с учётом чистого Windows-компьютера.

## Основной тип задач

Главная задача — писать проекты по автоматизации на Python:
- создание БД в PostgreSQL;
- интеграции с API;
- запуск и разработка через Docker;
- работа в VS Code;
- развитие проекта без костылей.

При необходимости возможны проекты на Google Apps Script для Google Таблиц.

## Правила качества

Для всех проектов обязательны:
- правильность;
- стабильность;
- скорость;
- перспективность;
- идеальность.

Нельзя жертвовать качеством без причины.
Приоритет: делать решение правильным, устойчивым и удобным для дальнейшего развития.

## Правила для Google Apps Script

Если задача связана с GAS:
- минимизируй вызовы к Sheets;
- минимизируй вызовы к UrlFetch;
- используй batch read/write;
- избегай лишних проходов по данным;
- предлагай быстрые и экономичные решения.

## Правила работы в этом репозитории

Перед выполнением любой новой задачи:
1. сначала прочитай:
   - `.codex/PROJECT_CONTEXT.md`
   - `.codex/TASKS.md`
   - `.codex/DECISIONS.md`
2. потом кратко перескажи, как ты понял проект;
3. перечисли текущие задачи;
4. только после этого предлагай изменения.

Если каких-то данных не хватает:
- не выдумывай;
- прямо указывай:
  - `не найдено`,
  - `не обнаружено`,
  - `требует уточнения`.

После заметных изменений:
- обновляй `.codex/TASKS.md`;
- при необходимости обновляй `.codex/DECISIONS.md`.

Не делай широкий рефакторинг без необходимости.
Изменения должны быть минимальными, проверяемыми и обратимыми.

---

# Repository Guidelines

## Project Structure & Module Organization
This repository is a Python parser for `lemanapro.ru` catalog pages. Core code lives in `lemana_parser/`:

- `cli.py` is the main command flow.
- `config.py` reads `.env` settings and CLI overrides.
- `catalog.py` and `products.py` collect catalog pages and product cards.
- `parsers/html.py` contains HTML extraction helpers.
- `http_utils.py` manages async HTTP sessions and retries.
- `excel_writer.py` writes `.xlsx` output.
- `auth/` and `diagnostics/` handle cookies and checks.
- Root `main.py`, `check_cookie.py`, and `cookie_grabber.py` are Windows-friendly wrappers.
- `scripts/` contains local test/check/cleanup helper scripts.
- `tests/` contains parser unit tests.
- `output/`, `parser.log`, `.env`, and `.venv/` are local runtime artifacts.

## Build, Test, and Development Commands

Primary Windows setup:

```bat
setup_win.bat
```

Run locally on Windows:

```bat
run_win.bat --url "https://lemanapro.ru/catalogue/..." --max-products 100
```

Run tests on Windows:

```bat
scripts\test_win.bat
```

WSL/Linux development equivalent:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
scripts/test_dev.sh
```

Use `.venv\Scripts\python.exe main.py --check-cookie --no-pause` or `.venv\Scripts\python.exe check_cookie.py` to diagnose authentication. Windows users can also run `get_cookie.bat`.

Install dev tools with `.venv\Scripts\python.exe -m pip install -r requirements-dev.txt`. Use `scripts\lint_win.bat`, `scripts\format_win.bat`, and `scripts\check_win.bat` before commits. Use `scripts\clean_dev.bat` after local runs if generated artifacts appear.

## Coding Style & Naming Conventions

Follow standard Python style with 4-space indentation, descriptive snake_case names, and small functions focused on parsing, fetching, or writing. Keep async network code in async functions and preserve the existing split between catalog collection, product parsing, configuration, and output writing. User-facing messages are mostly Russian; keep new CLI/log messages consistent.

Ruff is configured in `pyproject.toml`. Use `scripts\lint_win.bat` to check style and `scripts\format_win.bat` to format touched files. Prefer clean modular boundaries and consistent naming over large mixed-purpose files.

## Testing Guidelines

Tests use `unittest` and should be run through the project virtual environment:

```bat
.venv\Scripts\python.exe -m unittest discover -s tests
```

Place new tests in `tests/` using `test_*.py` names. Prefer deterministic HTML fixtures for parser behavior, and mock network calls for fetch failures or retry scenarios. Cover price parsing, image extraction, characteristics, summaries, and cookie-sensitive flows.

## Commit & Pull Request Guidelines

The history uses short imperative commit summaries, for example `Apply .gitignore and remove ignored files from tracking`. Keep commits focused and describe the user-visible change or maintenance task.

Pull requests should include a brief description, verification commands, and configuration notes. Link related issues when available. Include sample output paths or screenshots only when changing Excel output, CLI behavior, or Windows scripts.

## Security & Configuration Tips

Do not commit `.env`, cookies, generated Excel files, logs, virtual environments, build artifacts, or `*:Zone.Identifier` files. Use `.env.example` as the template for new configuration keys. When sharing failures, redact `LEMANA_COOKIE` and any request headers that could identify a session.
