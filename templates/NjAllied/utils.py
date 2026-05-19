"""Shared helpers used by every NjAllied section parser."""

import re
from datetime import datetime

MONEY_RE = re.compile(r"\$?\s*([\d,]+\.\d{2})")
DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
CODE_RE = re.compile(r"^\d{7}$")
SIZE_TOKENS = {
    "50ML", "100ML", "187ML", "200ML", "250ML", "355ML", "375ML",
    "500ML", "700ML", "750ML", "1.5L", "1.75L", "3L", "5L", "6L",
    "LITER", "L", "19.5L", "20LIT",
}


def parse_money(s):
    """Pull the first money value out of a string. Returns float or None."""
    if s is None:
        return None
    m = MONEY_RE.search(str(s).replace(",", ""))
    if not m:
        return None
    return float(m.group(1))


def parse_date(s):
    """Parse M/D/YYYY into a date. Returns date or None."""
    if s is None:
        return None
    m = DATE_RE.search(str(s))
    if not m:
        return None
    return datetime(int(m.group(3)), int(m.group(1)), int(m.group(2))).date()


def is_product_code(token):
    """A product code is exactly 7 digits."""
    return bool(token) and bool(CODE_RE.match(str(token).strip()))


def looks_like_size(token):
    if not token:
        return False
    t = str(token).strip().upper().replace(" ", "")
    if t in SIZE_TOKENS:
        return True
    # Numeric + ML or L
    return bool(re.match(r"^[\d.]+\s*(ML|L|LIT)$", t))


def clean(s):
    """Collapse whitespace and strip."""
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()


def split_first_money(line):
    """Split a line into (left-text, money-and-rest). Money-and-rest starts at the first $.
    Returns (left, rest) where rest starts with the $ char, or (line, '') if no $ found.
    """
    idx = line.find("$")
    if idx < 0:
        return line, ""
    return line[:idx].rstrip(), line[idx:]
