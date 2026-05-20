"""
utils.py — HTML-парсинг и форматирование. Портированы хелперы из GAS.
Нет зависимостей кроме стандартной библиотеки.
"""
import re


# ─── Строковые хелперы ────────────────────────────────────────────────────────

def strip_html(s: str) -> str:
    """Убираем все HTML-теги, схлопываем пробелы."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", s or "")).strip()


def decode_html(s: str) -> str:
    return (s or "").replace("&nbsp;", " ").replace("&#160;", " ")


def remove_spaces(s: str) -> str:
    return re.sub(r"[\s\u00a0\u202f]+", "", s or "")


def match1(text: str, pattern: str, flags: int = re.IGNORECASE | re.DOTALL) -> str:
    m = re.search(pattern, text or "", flags)
    return m.group(1) if m and m.lastindex else ""


# ─── Форматирование чисел ─────────────────────────────────────────────────────

def normalize_number(s: str) -> str:
    t = remove_spaces(str(s or "")).replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)", t)
    return m.group(1) if m else ""


def format_fixed(raw: str, digits: int) -> str:
    num = normalize_number(raw)
    if not num:
        return ""
    try:
        return f"{float(num):.{digits}f}".replace(".", ",")
    except ValueError:
        return ""


def format_var(raw: str) -> str:
    num = normalize_number(raw)
    return num.replace(".", ",") if num else ""


# ─── URL хелперы ─────────────────────────────────────────────────────────────

def extract_article_from_url(url: str) -> str:
    m = re.search(r"(\d{5,})/?$", url or "")
    return m.group(1) if m else ""


def extract_base_url(url: str) -> str:
    m = re.match(r"(https?://[^/]+)", url or "")
    return m.group(1) if m else ""


def normalize_url(href_or_url: str, base_url: str) -> str:
    if not href_or_url:
        return ""
    if re.match(r"https?://", href_or_url, re.I):
        return href_or_url
    base = base_url.rstrip("/")
    return base + (href_or_url if href_or_url.startswith("/") else "/" + href_or_url)


# ─── Парсинг цены ─────────────────────────────────────────────────────────────

def _extract_price_integer_primary(html: str) -> str:
    """Цена только из span с style=var(--text-primary) — актуальная, не перечёркнутая."""
    m = re.search(
        r'<span[^>]*data-testid=["\']price-integer["\'][^>]*'
        r'style=["\'][^"\']*var\(--text-primary\)[^"\']*["\'][^>]*>([\s\S]*?)</span>',
        html or "", re.I
    )
    if not m:
        return ""
    return remove_spaces(decode_html(strip_html(m.group(1))))


def parse_price_from_html(html: str) -> str:
    int_part = _extract_price_integer_primary(html)
    if not int_part:
        return ""
    frac_raw = (
        strip_html(match1(html, r'data-testid=["\']price-fraction["\'][^>]*>([\s\S]*?)</span>'))
        or strip_html(match1(html, r'data-testid=["\']price-decimal["\'][^>]*>([\s\S]*?)</span>'))
    ).strip()
    if not frac_raw:
        return int_part
    frac = re.sub(r"\D", "", remove_spaces(frac_raw))
    if len(frac) == 1:
        frac += "0"
    frac = frac[:2]
    return f"{int_part},{frac}"


# ─── Парсинг изображения ──────────────────────────────────────────────────────

def extract_main_image(html: str) -> str:
    og = match1(html, r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']')
    if og:
        return og
    item = match1(html, r'itemprop=["\']image["\'][^>]+content=["\']([^"\']+)["\']')
    if item:
        return item
    for m in re.finditer(
        r'https?://[^"\'<> \n\r\t]+?\.(?:jpg|jpeg|png|webp)(?:\?[^"\'<> \n\r\t]*)?',
        html or "", re.I
    ):
        u = m.group(0)
        if re.search(r"logo|icon|sprite|favicon", u, re.I):
            continue
        return u
    return ""


# ─── Парсинг характеристик ────────────────────────────────────────────────────

def extract_characteristics_section(html: str) -> str:
    idx = re.search(r'id=["\']characteristics["\']', html or "", re.I)
    if not idx:
        return ""
    tail = html[idx.start():]
    end = re.search(r"</section>", tail, re.I)
    return tail[: end.start() + 10] if end else tail[:20000]


def extract_all_characteristics(html: str) -> dict:
    section = extract_characteristics_section(html) or (html or "")
    result = {}
    for m in re.finditer(
        r'data-qa=["\']characteristics-list-item["\'][^>]*>'
        r'\s*<div[^>]*>([\s\S]*?)</div>\s*<div[^>]*>([\s\S]*?)</div>',
        section, re.I
    ):
        label = strip_html(m.group(1)).strip()
        value = re.sub(r"\s+", " ", strip_html(m.group(2))).strip()
        if label and value and label not in result:
            result[label] = value
    return result
