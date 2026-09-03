"""Algolia-hakuindeksi suoraan (HTTP, ei selainta).

Allekirjoitettu avain haetaan sivuston omasta rajapinnasta (voimassa ~2 h).
cfg: {key, signed_key_url, referer, app_id, index, facet_filters: [["attr:arvo"], ...],
      product_url_field (oletus "url"), hits_per_page, max_pages}
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from core.models import Product

from .http import get, session

_PREORDER_RE = re.compile(r"ennakko|julkaisu|pre-?order", re.I)
_AGENT = "Algolia for JavaScript (5.56.0); Lite (5.56.0); Browser"


def _headers(referer: str) -> dict:
    origin = "/".join(referer.split("/", 3)[:3])
    return {
        "Accept": "application/json, text/plain, */*",
        "Referer": referer,
        "Origin": origin,
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Upgrade-Insecure-Requests": "0",
    }


def _future(iso: str | None) -> bool:
    if not iso:
        return False
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")) > datetime.now(timezone.utc)
    except ValueError:
        return False


def _to_product(h: dict, key: str, url_field: str) -> Product:
    pid = str(h.get("objectID"))
    name = (h.get("title") or h.get("name") or "").strip()
    price = (h.get("price") or {}).get("amount")
    ws = h.get("wholeSaleStock") or {}
    display = str(ws.get("display") or "").strip()

    preorder = _future(h.get("presaleDate")) or _future(h.get("releaseDate")) \
        or bool(_PREORDER_RE.search(name))
    buyable = bool(h.get("isBuyableOnline")) and bool(ws.get("inStock"))
    in_stock = buyable and not preorder

    if preorder:
        status = "Ennakkotilaus"
    elif in_stock:
        status = f"{display} kpl saatavilla" if display else "Saatavilla"
    else:
        status = "Ei saatavilla"

    return Product(
        key=f"{key}:{pid}",
        name=name or f"Tuote {pid}",
        url=h.get(url_field) or h.get("url") or h.get("productUrl") or "",
        price=float(price) if isinstance(price, (int, float)) else None,
        in_stock=in_stock,
        preorder=preorder,
        status=status,
    )


def fetch(cfg: dict) -> list[Product]:
    key = cfg["key"]
    referer = cfg["referer"]
    app_id = cfg["app_id"]
    query_url = f"https://{app_id.lower()}-dsn.algolia.net/1/indexes/*/queries"
    headers = _headers(referer)

    api_key = get(cfg["signed_key_url"], headers=headers, retries=6).json()["apiKey"]
    params = {
        "x-algolia-application-id": app_id,
        "x-algolia-api-key": api_key,
        "x-algolia-agent": _AGENT,
    }
    out: dict[str, Product] = {}
    for page in range(0, cfg.get("max_pages", 5)):
        body = {"requests": [{
            "indexName": cfg["index"],
            "query": "",
            "hitsPerPage": cfg.get("hits_per_page", 100),
            "page": page,
            "facetFilters": cfg.get("facet_filters", []),
        }]}
        r = session().post(query_url, params=params, json=body, headers=headers, timeout=30)
        r.raise_for_status()
        res = r.json()["results"][0]
        for h in res.get("hits", []):
            p = _to_product(h, key, cfg.get("product_url_field", "url"))
            out[p.key] = p
        if page + 1 >= res.get("nbPages", 1):
            break
    return list(out.values())
