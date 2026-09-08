"""Bazaar-verkkokauppa-alusta. Kategoriasivut, tuotekortit div.products.

cfg: {key, base, categories: [polku, ...], max_pages, items_per_page}
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from core.models import Product

from .http import get

_PRICE_RE = re.compile(r"(\d[\d\s]*[.,]\d{2})")
_PREORDER_NAME = re.compile(r"presale|pre-?order|ennakko", re.I)


def _price(text: str) -> float | None:
    m = _PRICE_RE.search((text or "").replace("\xa0", " "))
    return float(m.group(1).replace(" ", "").replace(",", ".")) if m else None


def _parse_card(card, base: str, key: str) -> Product | None:
    a = card.select_one(".name a.header") or card.select_one('a[href*="/p/"]')
    if not a or not a.get("href"):
        return None
    href = a["href"].split("?")[0]
    m = re.search(r"/p/[^/]+/(\d+)", href)
    pid = m.group(1) if m else href.rstrip("/").rsplit("/", 1)[-1]
    name = a.get_text(" ", strip=True) or a.get("title", "").strip()

    price_el = card.select_one(".price-display .nowrap") or card.select_one(
        ".price-display .float-left"
    )
    price = _price(price_el.get_text(" ", strip=True)) if price_el else None

    label = card.select_one(".thumb .label")
    label_txt = label.get_text(strip=True).lower() if label else ""

    buyable = card.select_one("a.button.cart.buy") is not None
    can_alert = card.select_one("a.button.alert") is not None

    preorder = "presale" in label_txt or bool(_PREORDER_NAME.search(name))
    in_stock = buyable and not preorder
    status = (
        "Ennakkomyynti" if preorder
        else "Varastossa" if in_stock
        else "Loppunut" if can_alert
        else "Ei saatavilla"
    )
    return Product(
        key=f"{key}:{pid}",
        name=name,
        url=href if href.startswith("http") else f"{base}{href}",
        price=price,
        in_stock=in_stock,
        preorder=preorder and not in_stock,
        status=status,
    )


def fetch(cfg: dict) -> list[Product]:
    base = cfg["base"].rstrip("/")
    key = cfg["key"]
    max_pages = cfg.get("max_pages", 10)
    items = cfg.get("items_per_page", 144)
    out: dict[str, Product] = {}
    for cat in cfg["categories"]:
        prev_first = None
        for page in range(1, max_pages + 1):
            r = get(f"{base}{cat}", params={"sort": "name", "page": page, "items": items})
            soup = BeautifulSoup(r.text, "lxml")
            cards = soup.select("div.products[data-ga4-list]")
            if not cards:
                break
            first_a = cards[0].select_one('a[href*="/p/"]')
            first = first_a["href"].split("?")[0] if first_a else None
            if first and first == prev_first:
                break
            prev_first = first
            for c in cards:
                p = _parse_card(c, base, key)
                if p:
                    out[p.key] = p
            if len(cards) < items:
                break
    return list(out.values())
