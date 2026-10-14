"""Logo color analysis for automatic brand-matched previews.

Given a logo URL, downloads it safely, extracts the dominant vivid color,
and returns the best-matching built-in theme plus a custom accent color
derived from the logo — so a personalized preview instantly looks
'expensive and on-brand' without touching the shared database.
"""
import colorsys
import io

import httpx
from PIL import Image

_cache: dict[str, dict] = {}          # in-memory cache by logo URL
MAX_BYTES = 3 * 1024 * 1024


def _is_vivid(p) -> bool:
    r, g, b = p
    mx, mn = max(p), min(p)
    sat = 0 if mx == 0 else (mx - mn) / mx
    lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
    return sat > 0.25 and 0.15 < lum < 0.9


async def analyze_logo(url: str) -> dict:
    """Returns {'theme': ..., 'accent': '#hex', 'accent_ink': '#hex'} or {} on any failure."""
    if not url or not url.startswith(("http://", "https://")):
        return {}
    if url in _cache:
        return _cache[url]
    try:
        async with httpx.AsyncClient(timeout=6, follow_redirects=True) as client:
            resp = await client.get(url)
            data = resp.content
        if len(data) > MAX_BYTES:
            return {}
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.thumbnail((48, 48))
        pixels = list(img.getdata())
        vivid = [p for p in pixels if _is_vivid(p)] or pixels
        n = len(vivid)
        r, g, b = (sum(p[i] for p in vivid) // n for i in range(3))

        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        hue, lum = h * 360, (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255

        # accent: the logo's hue, pushed to look rich on both dark & light bg
        ar, ag, ab = colorsys.hsv_to_rgb(h, max(s, 0.55), max(v, 0.75))
        accent = "#%02x%02x%02x" % tuple(int(x * 255) for x in (ar, ag, ab))
        accent_lum = 0.2126 * ar + 0.7152 * ag + 0.0722 * ab
        accent_ink = "#12100b" if accent_lum > 0.55 else "#ffffff"

        if 20 <= hue <= 60:
            theme = "gold"
        elif hue >= 320 or hue < 15:
            theme = "rose"
        elif lum > 0.6:
            theme = "dark"
        else:
            theme = "light"

        result = {"theme": theme, "accent": accent, "accent_ink": accent_ink}
        _cache[url] = result
        return result
    except Exception:
        return {}
