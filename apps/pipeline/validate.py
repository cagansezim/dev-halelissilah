from __future__ import annotations
import re
from typing import Optional
from babel.numbers import parse_decimal
import dateparser

def parse_amount(s: str, locale: str = "tr_TR") -> Optional[float]:
    s = s.strip().replace("\u00a0"," ")
    try:
        return float(parse_decimal(s, locale=locale))
    except Exception:
        try:
            import re as _re
            return float(_re.sub(r"[^\d\.\-]", "", s))
        except Exception:
            return None

DATE_RX = re.compile(r"\b(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}[./-]\d{1,2}[./-]\d{1,2})\b")

def parse_date(s: str, languages=("tr","en")) -> Optional[str]:
    m = DATE_RX.search(s)
    if not m: return None
    dt = dateparser.parse(m.group(1), languages=list(languages))
    return dt.date().isoformat() if dt else None

CURRENCY_RX = re.compile(r"(TRY|TL|₺|USD|\$|EUR|€)", re.I)
def detect_currency(text: str, default: str = "TRY") -> str:
    m = CURRENCY_RX.search(text)
    if not m: return default
    sym = m.group(1).upper()
    if sym in ("TL","₺"): return "TRY"
    if sym in ("€",): return "EUR"
    if sym in ("$",): return "USD"
    return sym
