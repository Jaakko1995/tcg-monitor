"""Next.js -sivusto jossa tuotteet ovat __NEXT_DATA__ -JSONin props.pageProps.products.

Ei julkista varastosaldoa; käytetään "myydään verkossa" -lippua.
cfg: {key, base, category_path, product_path (oletus /tuote/), page_size, max_pages}
"""
from __future__ import annotations

import json
import re

from core.models import Product

from .http import get

_NEXT_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_PREORDER_RE = re.compile(r"ennakko|julkaisu|tulossa|pre-?order", re.I)


_FLIGHT_RE = re.compile(r'self\.__next_f\.push\(\[\d+,("(?:[^"\\]|\\.)*")\]\)')


def _products_from_flight(text: str) -> list[dict]:
    """Next.js App Router: tuotteet ovat self.__next_f.push -palasissa (escapettu JSON)."""
    try:
        flight = "".join(json.loads(c) for c in _FLIGHT_RE.findall(text))
        i = flight.find('"products":[')
        if i < 0:
            return []
        arr, _ = json.JSONDecoder().raw_decode(flight[i + len('"products":'):])
    except ValueError:
        return []
    return [p for p in arr if isinstance(p, dict)]


def _products_from_html(text: str) -> list[dict]:
    m = _NEXT_RE.search(text)
    if m:
        data = json.loads(m.group(1))
        found = data.get("props", {}).get("pageProps", {}).get("products", []) or []
        if found:
            return found
    return _products_from_flight(text)


def _to_product(raw: dict, base: str, key: str, product_path: str) -> Product:
    name = (raw.get("productName") or "").strip()
    slug = raw.get("slug") or raw.get("sokId", "")
    sok = str(raw.get("sokId") or slug)
    cents = raw.get("finalPrice") if raw.get("finalPrice") is not None else raw.get("price")
    price = round(cents / 100, 2) if isinstance(cents, (int, float)) else None
    ecom = bool(raw.get("isAllowedToBeSoldInEcom")) and bool(raw.get("salesChannels"))
    preorder = bool(_PREORDER_RE.search(name))
    return Product(
        key=f"{key}:{sok}",
        name=name,
        url=f"{base}{product_path}{slug}",
        price=price,
        in_stock=ecom and not preorder,
        preorder=preorder,
        status="Myynnissä verkossa" if ecom else "Ei verkkomyynnissä",
    )


def fetch(cfg: dict) -> list[Product]:
    base = cfg["base"].rstrip("/")
    key = cfg["key"]
    category_path = cfg["category_path"]
    product_path = cfg.get("product_path", "/tuote/")
    page_size = cfg.get("page_size", 48)
    max_pages = cfg.get("max_pages", 8)

    out: dict[str, Product] = {}
    prev_first = None
    for page in range(1, max_pages + 1):
        r = get(f"{base}{category_path}", params={"page": page})
        raws = _products_from_html(r.text)
        if not raws:
            break
        first = raws[0].get("slug")
        if first == prev_first:
            break
        prev_first = first
        for raw in raws:
            p = _to_product(raw, base, key, product_path)
            p.status = f"{p.status} · {raw.get('brandName', '')}".strip(" ·")
            out[p.key] = p
        if len(raws) < page_size:
            break
    return list(out.values())
