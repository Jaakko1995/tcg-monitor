"""Wix Stores -kategoriasivut (Playwright). [data-hook=product-item-root].

cfg: {key, base, categories: [slug, ...], max_pages}
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from core.models import Product

from .browser import browser_page, render

_PRICE_RE = re.compile(r"(?:€|EUR)\s*(\d[\d\s]*[.,]\d{2})|(\d[\d\s]*[.,]\d{2})\s*(?:€|EUR)")
_PRICE_ANY = re.compile(r"(\d[\d\s]*[.,]\d{2})")
_OOS_RE = re.compile(r"out of stock|sold out|loppu", re.I)
_PREORDER_RE = re.compile(r"pre-?order|ennakko|coming soon", re.I)


def _parse(html: str, base: str, key: str) -> list[Product]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for tile in soup.select('[data-hook="product-item-root"]'):
        slug = tile.get("data-slug", "")
        a = tile.select_one('a[href*="/product-page/"]')
        if not (slug or a):
            continue
        href = a["href"] if a else f"{base}/product-page/{slug}"
        slug = slug or href.rstrip("/").split("/")[-1]

        name_el = tile.select_one('[data-hook="product-item-name"]')
        name = name_el.get_text(" ", strip=True) if name_el else slug

        text = tile.get_text(" ", strip=True)
        price_el = tile.select_one(
            '[data-hook="product-item-price-to-pay"], [data-hook="sr-product-item-price-to-pay"], '
            '[data-hook="prices-container"]'
        )
        price_src = price_el.get_text(" ", strip=True) if price_el else text
        pm = _PRICE_RE.search(price_src) or _PRICE_ANY.search(price_src)
        price = None
        if pm:
            raw = next(g for g in pm.groups() if g) if pm.groups() else pm.group(0)
            price = float(raw.replace(" ", "").replace(",", "."))
        oos = bool(_OOS_RE.search(text))
        preorder = bool(_PREORDER_RE.search(text))
        add_btn = tile.select_one('[data-hook="product-item-add-to-cart-button"]')
        buyable = add_btn is not None and not _OOS_RE.search(add_btn.get_text(" ", strip=True))

        in_stock = buyable and not oos and not preorder
        out.append(Product(
            key=f"{key}:{slug}",
            name=name,
            url=href,
            price=price,
            in_stock=in_stock,
            preorder=preorder,
            status="Ennakko" if preorder else ("Varastossa" if in_stock else "Loppuunmyyty"),
        ))
    return out


def fetch(cfg: dict) -> list[Product]:
    base = cfg["base"].rstrip("/")
    key = cfg["key"]
    max_pages = cfg.get("max_pages", 4)
    out: dict[str, Product] = {}
    with browser_page() as page:
        for cat in cfg["categories"]:
            prev_first = None
            for pg in range(1, max_pages + 1):
                url = f"{base}/category/{cat}" + (f"?page={pg}" if pg > 1 else "")
                html = render(page, url, wait_selector='[data-hook="product-item-root"]',
                              wait_timeout=8000, scrolls=2)
                products = _parse(html, base, key)
                if not products or products[0].key == prev_first:
                    break
                prev_first = products[0].key
                for p in products:
                    out[p.key] = p
                if len(products) < 20:
                    break
    return list(out.values())
