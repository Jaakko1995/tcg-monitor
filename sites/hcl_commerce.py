"""HCL Commerce + Next.js. Tuotteet __NEXT_DATA__ props.pageProps.fallback -välimuistista.

Kategoriasivu palauttaa enintään ~60 tuotetta kerralla.
cfg: {key, url (kategoriasivu), product_base}
"""
from __future__ import annotations

import json
import re

from core.models import Product

from .http import get

_NEXT_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_PREORDER_RE = re.compile(
    r"ennakko|julkaisu|tulossa|pre-?order|\b\d{1,2}\.\d{1,2}\.20\d\d\b", re.I
)


def _find_listing(fallback: dict) -> list[dict]:
    for value in fallback.values():
        if (
            isinstance(value, dict)
            and isinstance(value.get("contents"), list)
            and len(value["contents"]) > 3
        ):
            return value["contents"]
    return []


def _price(raw: dict) -> float | None:
    prices = raw.get("price") or []
    by_usage = {p.get("usage"): p.get("value") for p in prices if isinstance(p, dict)}
    for usage in ("Display", "Offer"):
        v = by_usage.get(usage)
        if isinstance(v, (int, float)):
            return float(v)
    gp = raw.get("groupingProperties") or {}
    try:
        return float(gp.get("groupMinPriceValue"))
    except (TypeError, ValueError):
        return None


def _to_product(raw: dict, key: str, product_base: str) -> Product:
    name = (raw.get("name") or "").strip()
    pid = str(raw.get("partNumber") or raw.get("id"))
    seo = raw.get("seo") or {}
    href = seo.get("href") if isinstance(seo, dict) else None
    url = f"{product_base}{href}" if href else product_base

    buyable = str(raw.get("buyable")).lower() == "true"
    preorder = bool(_PREORDER_RE.search(name))
    return Product(
        key=f"{key}:{pid}",
        name=name,
        url=url,
        price=_price(raw),
        in_stock=buyable and not preorder,
        preorder=preorder,
        status=("Ennakko" if preorder else "Ostettavissa" if buyable else "Ei saatavilla"),
    )


def fetch(cfg: dict) -> list[Product]:
    key = cfg["key"]
    product_base = cfg["product_base"].rstrip("/")
    html = get(cfg["url"]).text
    m = _NEXT_RE.search(html)
    if not m:
        raise RuntimeError("__NEXT_DATA__ puuttuu")
    data = json.loads(m.group(1))
    fallback = data.get("props", {}).get("pageProps", {}).get("fallback", {})
    out: dict[str, Product] = {}
    for raw in _find_listing(fallback):
        p = _to_product(raw, key, product_base)
        out[p.key] = p
    return list(out.values())
