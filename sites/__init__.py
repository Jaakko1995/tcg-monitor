"""Seurattavien kohteiden rekisteri — ladataan konfiguraatiosta (core.config).

Kohteiden nimet ja osoitteet EIVÄT ole versionhallinnassa. Tämä moduuli sisältää
vain geneerisen logiikan: tyyppi -> hakumoduuli.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Callable

from core import config as _config
from core.models import Product

from . import (
    algolia,
    hcl_commerce,
    finqu,
    nextdata_products,
    oscar_cf,
    retail_search_api,
    shopify,
    sumup,
    wix_stores,
    woocommerce,
)

# tyyppi -> hakufunktio(cfg) -> list[Product]
FETCHERS: dict[str, Callable[[dict], list[Product]]] = {
    "woocommerce": woocommerce.fetch,
    "shopify": shopify.fetch,
    "algolia": algolia.fetch,
    "hcl_commerce": hcl_commerce.fetch,
    "finqu": finqu.fetch,
    "sumup": sumup.fetch,
    "nextdata_products": nextdata_products.fetch,
    "retail_search_api": retail_search_api.fetch,
    "oscar_cf": oscar_cf.fetch,
    "wix_stores": wix_stores.fetch,
}


@dataclass
class Site:
    name: str
    label: str
    group: str
    fetch: Callable[[], list[Product]]
    require_any: list[str] = field(default_factory=list)
    exclude_any: list[str] = field(default_factory=list)
    best_effort: bool = False


def _build() -> list[Site]:
    cfg = _config.load()
    filt = cfg.get("filters", {})
    exclude_all = filt.get("exclude_all", [])       # kaikille kohteille
    exclude_broad = filt.get("exclude_broad", [])   # kun exclude_broad: true
    require_default = filt.get("require_default", [])  # kun require: true

    sites: list[Site] = []
    for s in cfg["sites"]:
        fetcher = FETCHERS[s["type"]]
        params = dict(s.get("params", {}))
        params["key"] = s["key"]

        require = list(s.get("require_any", []))
        if s.get("require"):
            require += require_default
        exclude = list(s.get("exclude_any", [])) + exclude_all
        if s.get("exclude_broad", True):
            exclude += exclude_broad

        sites.append(Site(
            name=s["key"],
            label=s.get("label", s["key"]),
            group=s.get("group", "light"),
            fetch=(lambda f=fetcher, p=params, k=s["key"]: _fetch_opaque(f, p, k)),
            require_any=require,
            exclude_any=exclude,
            best_effort=bool(s.get("best_effort")),
        ))
    return sites


def _fetch_opaque(fetcher, params: dict, key: str) -> list[Product]:
    """Hae ja korvaa tuoteavaimen loppuosa hashilla -> committoitu state ei paljasta
    tuotteita (nimet/URLit ovat vain hetkellisesti muistissa ilmoituksia varten)."""
    prefix = key + ":"
    prods = fetcher(params)
    for p in prods:
        raw = p.key[len(prefix):] if p.key.startswith(prefix) else p.key
        p.key = prefix + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return prods


ALL_SITES: list[Site] = _build()
BY_NAME = {s.name: s for s in ALL_SITES}
LABELS = {s.name: s.label for s in ALL_SITES}


def select(group: str = "all", names: list[str] | None = None) -> list[Site]:
    if names:
        return [BY_NAME[n] for n in names if n in BY_NAME]
    if group == "all":
        return list(ALL_SITES)
    return [s for s in ALL_SITES if s.group == group]
