"""Vertaa edellistä tilaa ja tuoretta hakua -> tapahtumalista."""
from __future__ import annotations

from dataclasses import dataclass

from .models import Product
from .state import now_iso

NEW = "new"
BACK_IN_STOCK = "back_in_stock"
PREORDER_OPEN = "preorder_open"
PRICE_CHANGE = "price_change"

PRICE_EPS = 0.01

# Kuinka monta peräkkäistä ajoa tuote saa "kadota" ennen kuin se poistetaan tilasta.
# Suojaa valeilmoituksilta kun kaupan haku palauttaa hetkellisesti vajaan listan
# (esim. Verkkokaupan ML-rankattu haku, tai ajoittainen 403).
PURGE_AFTER_MISSES = 4


@dataclass
class Event:
    kind: str
    site: str
    product: Product
    old_price: float | None = None


def diff_site(
    site: str,
    old_products: dict,
    fresh: list[Product],
    *,
    seeded: bool,
) -> tuple[list[Event], dict]:
    """Palauttaa (tapahtumat, uusi products-dict tilaa varten).

    Jos seeded=False, tapahtumia ei synny (ensimmäinen ajo): tila vain täytetään.
    """
    events: list[Event] = []
    new_state: dict = {}
    ts = now_iso()
    fresh_keys = {p.key for p in fresh}

    for p in fresh:
        prev = old_products.get(p.key)
        entry = p.to_state()
        entry["first_seen"] = prev.get("first_seen", ts) if prev else ts
        entry["last_seen"] = ts
        # "missing"-laskuri nollautuu kun tuote taas löytyy
        new_state[p.key] = entry

        if not seeded:
            continue

        if prev is None:
            events.append(Event(NEW, site, p))
            continue

        # Tuote palasi "kadonneiden" listalta -> ei uusi. Verrataan viimeksi nähtyyn tilaan.
        was_in_stock = bool(prev.get("in_stock"))
        was_preorder = bool(prev.get("preorder"))
        old_price = prev.get("price")

        if p.in_stock and not was_in_stock:
            events.append(Event(BACK_IN_STOCK, site, p))
        elif p.preorder and not was_preorder and not p.in_stock:
            events.append(Event(PREORDER_OPEN, site, p))

        if (
            p.price is not None
            and old_price is not None
            and abs(float(p.price) - float(old_price)) >= PRICE_EPS
        ):
            events.append(Event(PRICE_CHANGE, site, p, old_price=float(old_price)))

    # Tuotteet jotka eivät olleet tässä haussa: pidetään tilassa muutama ajo (sticky),
    # ettei hetkellinen katoaminen aiheuta myöhemmin "uusi tuote" -ilmoitusta.
    for key, prev in old_products.items():
        if key in fresh_keys:
            continue
        misses = int(prev.get("missing_runs", 0)) + 1
        if misses >= PURGE_AFTER_MISSES:
            continue  # poistetaan lopullisesti
        kept = dict(prev)
        kept["missing_runs"] = misses
        new_state[key] = kept

    return events, new_state
