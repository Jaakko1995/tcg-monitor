"""Finqu-alusta. Kategoriasivut, tuotekortit .product-card-grid-item.

cfg: {key, base, categories: [polku, ...], max_pages}
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from core.models import Product

from .http import get

_PRICE_RE = re.compile(r"(\d[\d\s]*[.,]\d{2})")
_PREORDER_NAME = re.compile(r"julkaisup|ennakko|pre-?order", re.I)


def _price(text: str) -> float | None:
    m = _PRICE_RE.search((text or "").replace("\xa0", " "))
    return float(m.group(1).replace(" ", "").replace(",", ".")) if m else None


def _parse_card(card, base: str, key: str) -> Product | None:
    a = card.select_one("a[href^='/tuote/']")
    if not a:
        return None
    href = a["href"].split("?")[0]
    slug = href.rsplit("/", 1)[-1]

    name_el = card.select_one(".product-name-text")
    name = name_el.get_text(" ", strip=True) if name_el else a.get("title", slug)

    price_el = card.select_one(".product-price .text-price, .product-price")
    price = _price(price_el.get_text(" ", strip=True)) if price_el else None

    badges = {b.get_text(strip=True).lower() for b in card.select(".product-badge-content")}
    action = card.select_one(".product-action")
    action_txt = action.get_text(" ", strip=True).lower() if action else ""

    sold_out = "loppunut" in badges or "loppuunmyyty" in badges
    preorder = "ennakkomyynti" in badges or bool(_PREORDER_NAME.search(name))
    buyable = "ostoskori" in action_txt or "koriin" in action_txt

    in_stock = buyable and not sold_out and not preorder
    status = (
        "Loppunut" if sold_out
        else "Ennakkomyynti" if preorder
        else "Varastossa" if in_stock
        else "Ei ostettavissa"
    )
    return Product(
        key=f"{key}:{slug}",
        name=name,
        url=f"{base}{href}",
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
    for cat in cfg["categories"]:
        prev_first = None
        for page in range(1, max_pages + 1):
            r = get(f"{base}{cat}", params={"page": page})
            soup = BeautifulSoup(r.text, "lxml")
            grid = soup.select_one(".category-items")
            cards = grid.select(".product-card-grid-item") if grid else []
            if not cards:
                break
            first_a = cards[0].select_one("a[href^='/tuote/']")
            first_href = first_a["href"].split("?")[0] if first_a else None
            if first_href and first_href == prev_first:
                break
            prev_first = first_href
            for card in cards:
                p = _parse_card(card, base, key)
                if p:
                    out[p.key] = p
            if len(cards) < 100:
                break
    return list(out.values())
