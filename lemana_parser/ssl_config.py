"""Настройка проверки TLS-сертификатов для curl_cffi."""

from __future__ import annotations

import logging
import os
import shutil
from functools import lru_cache
from pathlib import Path

from lemana_parser.config import CONFIG

logger = logging.getLogger("ssl_config")


def _is_ascii_path(path: Path) -> bool:
    try:
        str(path).encode("ascii")
    except UnicodeEncodeError:
        return False
    return True


def _windows_ca_candidates() -> list[Path]:
    candidates: list[Path] = []
    program_data = os.environ.get("PROGRAMDATA")
    if program_data:
        candidates.append(Path(program_data) / "lemana-parser" / "cacert.pem")

    system_root = os.environ.get("SYSTEMROOT")
    if system_root:
        candidates.append(Path(system_root) / "Temp" / "lemana-parser-cacert.pem")

    candidates.append(Path("C:/Windows/Temp/lemana-parser-cacert.pem"))
    return [path for path in candidates if _is_ascii_path(path)]


def _copy_certifi_to_ascii_path(source: Path) -> str | None:
    for target in _windows_ca_candidates():
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists() or target.stat().st_size != source.stat().st_size:
                shutil.copyfile(source, target)
            return str(target)
        except OSError as exc:
            logger.debug("Не удалось подготовить CA bundle %s: %s", target, exc)
    return None


@lru_cache(maxsize=1)
def get_ssl_verify() -> bool | str:
    """
    Возвращает значение для параметра `verify` в curl_cffi.

    На Windows libcurl может падать с `curl (77)`, если путь к certifi содержит
    кириллицу. Поэтому для Windows копируем CA bundle в ASCII-путь и отдаём его
    явно. Если подготовить файл не удалось, возвращаем False как аварийный
    fallback, чтобы локальная проблема сертификатов не выглядела как протухшая
    cookie.
    """
    if not CONFIG["ssl_verify"]:
        return False

    if os.name != "nt":
        return True

    try:
        import certifi
    except ImportError:
        logger.warning(
            "certifi не установлен, curl_cffi будет использовать системные настройки TLS"
        )
        return True

    source = Path(certifi.where())
    if _is_ascii_path(source):
        return str(source)

    copied = _copy_certifi_to_ascii_path(source)
    if copied:
        logger.info("TLS CA bundle подготовлен для Windows: %s", copied)
        return copied

    logger.warning(
        "Не удалось подготовить CA bundle в ASCII-пути; временно отключаем TLS verify для curl_cffi"
    )
    return False
