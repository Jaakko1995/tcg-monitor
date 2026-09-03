"""Geneerinen WooCommerce Store API -hakija.

cfg: {key, base, category_ids: [...], max_pages}
Endpoint: <base>/wp-json/wc/store/v1/products?category=<id>&orderby=date&per_page=100
"""
from __future__ import annotations

import html as html_mod
import re

from core.models import Product

from .http import get

_TAG_RE = re.compile(r"<[^>]+>")
_PREORDER_HINT = re.compile(
    r"ennakko|julkaisup|pre-?order|tulossa|saapuu|coming soon|\b20\d\d\b.*(?:julка|ilmesty)",
    re.I,
)


def _clean(s: str) -> str:
    return html_mod.unescape(_TAG_RE.sub("", s or "")).strip()


def _price(prices: dict) -> float | None:
    if not prices:
        return None
    minor = prices.get("currency_minor_unit", 2)
    raw = prices.get("price")
    if raw in (None, ""):
        return None
    try:
        return int(raw) / (10 ** int(minor))
    except (ValueError, TypeError):
        return None


def _iter_pages_http(endpoint: str, cat_id: int, max_pages: int):
    page = 1
    while True:
        r = get(endpoint, params={
            "category": cat_id, "per_page": 100, "page": page,
            "orderby": "date", "order": "desc",
        })
        items = r.json()
        yield items
        total_pages = int(r.headers.get("x-wp-totalpages", "1") or "1")
        if not items or page >= total_pages or page >= max_pages:
            break
        page += 1


def fetch(cfg: dict) -> list[Product]:
    base = cfg["base"].rstrip("/")
    prefix = cfg["key"]
    endpoint = f"{base}/wp-json/wc/store/v1/products"
    max_pages = cfg.get("max_pages", 6)
    out: dict[str, Product] = {}

    for cat_id in cfg["category_ids"]:
        for items in _iter_pages_http(endpoint, cat_id, max_pages):
            for it in items or []:
                p = _to_product(base, prefix, it)
                out[p.key] = p
    return list(out.values())


def _to_product(base: str, prefix: str, it: dict) -> Product:
    name = _clean(it.get("name", ""))
    permalink = it.get("permalink") or ""
    key = f"{prefix}:{_key_from_permalink(permalink) or it.get('id')}"
    in_stock = bool(it.get("is_in_stock"))
    backorder = bool(it.get("is_on_backorder"))
    preorder = backorder or bool(_PREORDER_HINT.search(name))
    avail = _clean(it.get("stock_availability", {}).get("text", "")) if isinstance(
        it.get("stock_availability"), dict
    ) else ""
    if backorder and not avail:
        avail = "Jälkitoimitus / ennakko"
    return Product(
        key=key,
        name=name,
        url=permalink or base,
        price=_price(it.get("prices") or {}),
        in_stock=in_stock and not backorder,
        preorder=preorder,
        status=avail or ("Varastossa" if in_stock else "Ei varastossa"),
    )


def _key_from_permalink(url: str) -> str:
    m = re.search(r"/(?:tuote|product|p)/([^/?#]+)", url)
    if m:
        return m.group(1)
    return url.rstrip("/").split("/")[-1] if url else ""
