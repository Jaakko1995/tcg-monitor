"""Geneerinen Shopify-hakija (/collections/<handle>/products.json).

cfg: {key, domain, collections: [...], max_pages}
"""
from __future__ import annotations

import re

from core.models import Product

from .http import get

_PREORDER_RE = re.compile(r"ennakko|pre-?order|julkaisu|tulossa|coming soon", re.I)


def _price(variants: list[dict]) -> float | None:
    prices = []
    for v in variants:
        try:
            prices.append(float(v.get("price")))
        except (TypeError, ValueError):
            pass
    return min(prices) if prices else None


def _to_product(domain: str, prefix: str, raw: dict) -> Product:
    handle = raw.get("handle", "")
    variants = raw.get("variants", []) or []
    available = any(v.get("available") for v in variants)
    tags = raw.get("tags", [])
    tag_text = " ".join(tags) if isinstance(tags, list) else str(tags)
    blob = f"{raw.get('title','')} {tag_text} {raw.get('product_type','')}"
    preorder = bool(_PREORDER_RE.search(blob))
    return Product(
        key=f"{prefix}:{handle}",
        name=raw.get("title", "").strip(),
        url=f"https://{domain}/products/{handle}",
        price=_price(variants),
        in_stock=available and not preorder,
        preorder=preorder,
        status=(
            "Ennakko" if preorder
            else "Varastossa" if available
            else "Loppuunmyyty"
        ),
    )


def fetch(cfg: dict) -> list[Product]:
    domain = cfg["domain"]
    prefix = cfg["key"]
    out: dict[str, Product] = {}
    for handle in cfg["collections"]:
        for page in range(1, cfg.get("max_pages", 10) + 1):
            r = get(
                f"https://{domain}/collections/{handle}/products.json",
                params={"limit": 250, "page": page},
            )
            products = r.json().get("products", [])
            if not products:
                break
            for raw in products:
                p = _to_product(domain, prefix, raw)
                out[p.key] = p
            if len(products) < 250:
                break
    return list(out.values())
