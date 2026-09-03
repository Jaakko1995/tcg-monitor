"""osCommerce/Oscar-tyylinen listaus Cloudflare-haasteen takana (Playwright).

BEST-EFFORT: Cloudflare voi estää ajon GitHubin IP:stä.
cfg: {key, list_url, product_url, cpaths: [...], max_pages}
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from core.models import Product

from .browser import browser_page, render

_PRICE_RE = re.compile(r"(\d[\d\s]*[.,]\d{2})\s*€")
_PREORDER_RE = re.compile(r"ennakko|julkais|tulossa|pre-?order|saapuu", re.I)
_INSTOCK_RE = re.compile(r"varastossa", re.I)
_OOS_RE = re.compile(r"tilapäisesti loppu|loppuunmyyty|ei saatavilla|jälkitoimitus", re.I)


def _merge_cells(soup: BeautifulSoup) -> dict[str, dict]:
    prods: dict[str, dict] = {}
    for td in soup.select("td.productListing-data"):
        a = td.select_one('a[href*="products_id="]')
        if not a:
            continue
        m = re.search(r"products_id=(\d+)", a.get("href", ""))
        if not m:
            continue
        pid = m.group(1)
        d = prods.setdefault(pid, {"name": "", "price": None, "status": "", "buy": False})

        img = td.select_one("img[alt], img[title]")
        if img:
            nm = (img.get("title") or img.get("alt") or "").strip()
            if nm and len(nm) > len(d["name"]):
                d["name"] = nm

        text = td.get_text(" ", strip=True)
        pm = _PRICE_RE.search(text)
        if pm and d["price"] is None:
            d["price"] = float(pm.group(1).replace(" ", "").replace(",", "."))
        if td.select_one('a[href*="action=buy_now"]'):
            d["buy"] = True

        for rx in (_INSTOCK_RE, _OOS_RE, _PREORDER_RE):
            mm = rx.search(text)
            if mm and not d["status"]:
                seg = re.search(
                    r"(Varastossa[^.]*|Ennakko\w*[^.]*|Tilapäisesti loppu[^.]*|Jälkitoimitus[^.]*)",
                    text, re.I,
                )
                d["status"] = (seg.group(1) if seg else mm.group(0)).strip()[:120]
    return prods


def _parse(html: str, key: str, product_url: str) -> list[Product]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for pid, d in _merge_cells(soup).items():
        if not d["name"]:
            continue
        blob = f"{d['name']} {d['status']}"
        preorder = bool(_PREORDER_RE.search(blob))
        oos = bool(_OOS_RE.search(d["status"]))
        in_stock = bool(_INSTOCK_RE.search(d["status"])) and not oos and not preorder
        out.append(Product(
            key=f"{key}:{pid}",
            name=d["name"],
            url=product_url.format(pid=pid),
            price=d["price"],
            in_stock=in_stock,
            preorder=preorder,
            status=d["status"] or ("Ostettavissa" if d["buy"] else "?"),
        ))
    return out


def fetch(cfg: dict) -> list[Product]:
    key = cfg["key"]
    list_url = cfg["list_url"]
    product_url = cfg["product_url"]
    max_pages = cfg.get("max_pages", 8)

    out: dict[str, Product] = {}
    with browser_page() as page:
        for cpath in cfg["cpaths"]:
            prev_first = None
            for pg in range(1, max_pages + 1):
                html = render(
                    page, f"{list_url}?cPath={cpath}&page={pg}",
                    wait_selector="td.productListing-data", challenge_wait_ms=9000,
                )
                if "just a moment" in html.lower()[:2000]:
                    raise RuntimeError("Cloudflare-haaste esti sivun")
                products = _parse(html, key, product_url)
                if not products or products[0].key == prev_first:
                    break
                prev_first = products[0].key
                for p in products:
                    out[p.key] = p
                if len(products) < 20:
                    break
    if not out:
        raise RuntimeError("Ei tuotteita (mahdollinen Cloudflare-esto)")
    return list(out.values())
