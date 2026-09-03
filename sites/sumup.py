"""SumUp-alusta. Kategoriasivut, tuotteet a[data-selector=list-product-view].

cfg: {key, base, categories: [[polku, onko_ennakkokategoria], ...], max_pages}
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from core.models import Product

from .http import get

PAGE_SIZE = 16

_PRICE_RE = re.compile(r"(\d[\d\s]*[.,]\d{2})")
_PREORDER_NAME = re.compile(r"ennakko|julkaisu|pre-?order|tulossa|\(\d{1,2}\.\d{1,2}\.\d{4}\)", re.I)


def _price(text: str) -> float | None:
    m = _PRICE_RE.search((text or "").replace("\xa0", " "))
    return float(m.group(1).replace(" ", "").replace(",", ".")) if m else None


def _parse_card(a, is_preorder_cat: bool, key_prefix: str) -> Product | None:
    href = a.get("href", "")
    if "/tuote/" not in href:
        return None
    pid = a.get("data-item-id") or href.rstrip("/").split("/")[-1]
    name_el = a.select_one('h3[data-selector="os-theme-product-list-name"], h3')
    name = (name_el.get_text(" ", strip=True) if name_el else a.get("data-item-name", "")).strip()

    sold_out = a.select_one("span.product-sold-out-label") is not None
    price_el = a.select_one(
        '[data-selector="os-theme-product-list-price-sale"], '
        '[data-selector="os-theme-product-list-price-regular"]'
    )
    price = _price(price_el.get_text(" ", strip=True)) if price_el else _price(a.get_text(" ", strip=True))

    preorder = is_preorder_cat or bool(_PREORDER_NAME.search(name))
    in_stock = not sold_out and not preorder
    status = (
        "Loppuunmyyty" if sold_out
        else "Ennakkotilattavissa" if preorder
        else "Varastossa"
    )
    return Product(
        key=f"{key_prefix}:{pid}",
        name=name,
        url=href,
        price=price,
        in_stock=in_stock,
        preorder=preorder and not sold_out,
        status=status,
    )


def fetch(cfg: dict) -> list[Product]:
    base = cfg["base"].rstrip("/")
    key = cfg["key"]
    max_pages = cfg.get("max_pages", 10)
    out: dict[str, Product] = {}
    for path, is_pre in cfg["categories"]:
        prev_first = None
        for page in range(1, max_pages + 1):
            r = get(f"{base}{path}", params={"page": page})
            soup = BeautifulSoup(r.text, "lxml")
            cards = soup.select('a[data-selector="list-product-view"]')
            if not cards:
                break
            first = cards[0].get("href")
            if first == prev_first:
                break
            prev_first = first
            for a in cards:
                p = _parse_card(a, is_pre, key)
                if p:
                    out[p.key] = p
            if len(cards) < PAGE_SIZE:
                break
    return list(out.values())
