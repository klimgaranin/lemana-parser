"""Структурный debug-лог API-запросов без секретов."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from lemana_parser.config import CONFIG

logger = logging.getLogger("api.debug")

_SENSITIVE_HEADER_NAMES = {"authorization", "cookie", "set-cookie", "x-api-key"}
_LOG_PATH: Path | None = None
_CLEANED = False


def _now() -> datetime:
    return datetime.now().astimezone()


def _prepare_log_path() -> Path:
    global _LOG_PATH
    if _LOG_PATH is None:
        log_dir = Path(CONFIG["api_debug_log_dir"])
        log_dir.mkdir(parents=True, exist_ok=True)
        _LOG_PATH = log_dir / f"api_debug_{_now():%Y%m%d_%H%M%S}.jsonl"
    return _LOG_PATH


def cleanup_old_api_debug_logs() -> None:
    """Удаляет устаревшие API debug-логи по retention в днях."""
    global _CLEANED
    if _CLEANED or not CONFIG["api_debug_log_enabled"]:
        return
    _CLEANED = True

    retention_days = CONFIG["api_debug_log_retention_days"]
    if retention_days <= 0:
        return

    log_dir = Path(CONFIG["api_debug_log_dir"])
    if not log_dir.exists():
        return

    cutoff = _now() - timedelta(days=retention_days)
    removed = 0
    for path in log_dir.glob("api_debug_*.jsonl"):
        try:
            modified_at = datetime.fromtimestamp(path.stat().st_mtime).astimezone()
            if modified_at < cutoff:
                path.unlink()
                removed += 1
        except OSError as exc:
            logger.debug("Не удалось удалить старый API debug-log %s: %s", path, exc)
    if removed:
        logger.info("Удалено старых API debug-log файлов: %d", removed)


def get_api_debug_log_path() -> Path | None:
    if not CONFIG["api_debug_log_enabled"]:
        return None
    return _prepare_log_path()


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + f"... <truncated {len(value) - limit} chars>"


def _redact_headers(headers: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in headers.items():
        if key.lower() in _SENSITIVE_HEADER_NAMES:
            result[key] = "***redacted***"
        else:
            result[key] = value
    return result


def _response_text(response: Any) -> str:
    text = getattr(response, "text", "")
    if callable(text):
        try:
            text = text()
        except Exception:
            text = ""
    if isinstance(text, bytes):
        return text.decode("utf-8", errors="replace")
    return str(text or "")


def _safe_json(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
    except TypeError:
        return repr(value)
    return value


def write_api_debug_event(event: dict[str, Any]) -> None:
    if not CONFIG["api_debug_log_enabled"]:
        return
    cleanup_old_api_debug_logs()
    path = _prepare_log_path()
    event = {"ts": _now().isoformat(timespec="seconds"), **event}
    try:
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    except OSError as exc:
        logger.warning("Не удалось записать API debug-log %s: %s", path, exc)


def log_api_request(
    *,
    method: str,
    url: str,
    params: dict[str, Any],
    headers: dict[str, Any],
    payload: dict[str, Any],
    attempt: int,
) -> None:
    product_ids = payload.get("productIds")
    write_api_debug_event(
        {
            "event": "request",
            "method": method,
            "attempt": attempt,
            "url": url,
            "params": _safe_json(params),
            "headers": _redact_headers(headers),
            "payload": _safe_json(payload),
            "product_ids_count": len(product_ids) if isinstance(product_ids, list) else None,
        }
    )


def log_api_response(
    *,
    method: str,
    url: str,
    attempt: int,
    elapsed_ms: int,
    response: Any,
) -> None:
    headers = getattr(response, "headers", {}) or {}
    content_type = headers.get("content-type") or headers.get("Content-Type")
    body_limit = CONFIG["api_debug_log_body_limit"]
    body = _truncate(_response_text(response), body_limit)
    event = {
        "event": "response",
        "method": method,
        "attempt": attempt,
        "url": url,
        "status_code": getattr(response, "status_code", None),
        "elapsed_ms": elapsed_ms,
        "content_type": content_type,
        "headers": _redact_headers(dict(headers)),
    }
    if getattr(response, "status_code", 0) >= 400 or CONFIG["api_debug_log_success_body"]:
        event["body"] = body
    else:
        event["body_preview"] = body[:300]
    write_api_debug_event(event)
