"""Verkkokaupan sisäinen haku- + saatavuus-API (HTTP, ei selainta).

cfg: {key, base, search_url, avail_url, category, page_size, max_pages, avail_chunk}
"""
from __future__ import annotations

import uuid

from core.models import Product

from .http import get

_STATUS = {
    "InStock": "Varastossa",
    "LimitedAvailability": "Rajoitetusti saatavilla",
    "SoldOut": "Loppuunmyyty",
    "InStoreOnly": "Vain myymälässä",
    "PreOrder": "Ennakkotilaus",
}


def _search_ids(cfg: dict) -> list[dict]:
    base = cfg["base"].rstrip("/")
    headers = {"Accept": "application/vnd.api+json", "Origin": base, "Referer": base + "/"}
    page_size = cfg.get("page_size", 60)
    sid = str(uuid.uuid4())
    rows: list[dict] = []
    for page in range(1, cfg.get("max_pages", 8) + 1):
        url = (
            f"{cfg['search_url']}?filter%5Bbase%2Bcategory%5D%5B%5D={cfg['category']}"
            f"&page%5Bnumber%5D={page}&page%5Bsize%5D={page_size}"
            f"&sort=price&sessionId={sid}"
        )
        data = get(url, headers=headers).json().get("data", [])
        if not data:
            break
        rows.extend(data)
        if len(data) < page_size:
            break
    return rows


def _availability(cfg: dict, pids: list[str]) -> dict[str, dict]:
    base = cfg["base"].rstrip("/")
    headers = {"Accept": "application/json", "Origin": base, "Referer": base + "/"}
    chunk = cfg.get("avail_chunk", 24)
    out: dict[str, dict] = {}
    for i in range(0, len(pids), chunk):
        r = get(f"{cfg['avail_url']}?pids=" + ",".join(pids[i : i + chunk]), headers=headers)
        for a in r.json():
            out[str(a.get("pid"))] = a
    return out


def fetch(cfg: dict) -> list[Product]:
    base = cfg["base"].rstrip("/")
    key = cfg["key"]
    rows = _search_ids(cfg)
    pids = [str(r["id"]) for r in rows]
    avail = _availability(cfg, pids)

    out: list[Product] = []
    for r in rows:
        pid = str(r["id"])
        attr = r.get("attributes", {})
        name = attr.get("name", "").strip()
        href = attr.get("href") or f"/fi/product/{pid}"
        price = (attr.get("price") or {}).get("current")

        av = avail.get(pid, {})
        schema = (av.get("status") or {}).get("schema", "")
        preorder = bool(av.get("flags", {}).get("isPreorder"))
        purchasable = bool((av.get("stocks") or {}).get("shipment", {}).get("isPurchasable"))
        in_stock = purchasable and not preorder

        out.append(Product(
            key=f"{key}:{pid}",
            name=name or f"Tuote {pid}",
            url=base + href,
            price=float(price) if isinstance(price, (int, float)) else None,
            in_stock=in_stock,
            preorder=preorder,
            status=_STATUS.get(schema, schema or ("Varastossa" if in_stock else "Ei saatavilla")),
        ))
    return out
