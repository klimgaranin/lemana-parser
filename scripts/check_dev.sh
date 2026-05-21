#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

.venv/bin/python -m compileall -q main.py check_cookie.py cookie_grabber.py lemana_parser tests
.venv/bin/python -m unittest discover -s tests

