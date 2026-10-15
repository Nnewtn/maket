"""Frankfurter.app FX rates with 12-hour cache and offline fallback."""
from __future__ import annotations
import json
import time
import logging
import httpx

log = logging.getLogger("fx")

_CACHE_FILE = None  # disabled; memory only
_FALLBACK = {
    "base": "PLN",
    "rates": {"PLN": 1.0, "USD": 0.25, "EUR": 0.23},
    "date": "fallback",
    "ts": 0,
}
_mem_cache = dict(_FALLBACK)
_TTL = 12 * 3600


def get_rates(base: str = "PLN") -> dict:
    """Return rates + base + date. Memory cache, 12 h."""
    now = time.time()
    if _mem_cache.get("base") == base and (now - _mem_cache.get("ts", 0)) < _TTL:
        return _mem_cache
    try:
        url = f"https://api.frankfurter.app/latest?from={base}"
        with httpx.Client(timeout=6.0) as cx:
            r = cx.get(url)
        if r.status_code == 200:
            data = r.json()
            rates = data.get("rates", {})
            for need in ("PLN", "USD", "EUR"):
                rates.setdefault(need, _FALLBACK["rates"][need])
            _mem_cache.update({"base": base, "rates": rates, "date": data.get("date", ""), "ts": now})
            return _mem_cache
    except Exception as e:
        log.warning("fx fetch failed: %s", e)
    _mem_cache.update({**_FALLBACK, "ts": now})
    return _mem_cache


def convert(amount: float, from_ccy: str, to_ccy: str) -> float:
    if from_ccy == to_ccy:
        return amount
    rates = get_rates(from_ccy)["rates"]
    if to_ccy not in rates or from_ccy not in rates:
        return amount
    # amount in from_ccy → PLN → to_ccy
    pln = amount / rates[from_ccy]
    return round(pln * rates[to_ccy], 2)
