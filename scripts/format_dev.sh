#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

.venv/bin/python -m ruff format .
.venv/bin/python -m ruff check --fix . --no-cache
