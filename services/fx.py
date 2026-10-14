"""Currency conversion — live ECB rates via frankfurter.app (free, no API key),
with a 12h in-memory cache and static fallback so the site never breaks offline."""
import time

import httpx

SUPPORTED = ("PLN", "USD", "EUR")
SYMBOLS = {"PLN": "zł", "USD": "$", "EUR": "€"}

FALLBACK_PLN = {"PLN": 1.0, "USD": 0.25, "EUR": 0.23}

_cache = {"ts": 0.0, "base": None, "rates": None}
CACHE_TTL = 60 * 60 * 12


def _fallback(base: str) -> dict:
    per_pln = dict(FALLBACK_PLN)
    base_in_pln = 1.0 / per_pln[base]
    return {k: round(v * base_in_pln, 6) for k, v in per_pln.items()}


async def get_rates(base: str = "PLN") -> dict:
    if base not in SUPPORTED:
        base = "PLN"
    now = time.time()
    if _cache["rates"] and _cache["base"] == base and now - _cache["ts"] < CACHE_TTL:
        return {"base": base, "rates": _cache["rates"], "live": True}
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                "https://api.frankfurter.app/latest",
                params={"from": base, "to": ",".join(SUPPORTED)},
            )
            data = resp.json()
            rates = {c: float(data["rates"].get(c, 1.0)) for c in SUPPORTED}
            rates[base] = 1.0
            _cache.update(ts=now, base=base, rates=rates)
            return {"base": base, "rates": rates, "live": True}
    except Exception:
        return {"base": base, "rates": _fallback(base), "live": False}
