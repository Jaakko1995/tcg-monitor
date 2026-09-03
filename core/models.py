"""Yhteiset tietorakenteet."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Product:
    """Yksi tuote yhdessä kaupassa."""

    key: str            # vakaa tunniste kaupan sisällä (URL-polku tai SKU)
    name: str
    url: str
    price: Optional[float] = None
    in_stock: bool = False
    preorder: bool = False
    status: str = ""    # vapaa kuvaus ("Varastossa (3 kpl)", "Ennakkomyynti", ...)

    def to_state(self) -> dict:
        # Tilaan tallennetaan vain vertailuun tarvittavat kentät.
        # EI url/nimi/status -> julkiseen repoon committoitu state ei paljasta kohteita.
        return {
            "price": self.price,
            "in_stock": self.in_stock,
            "preorder": self.preorder,
        }


@dataclass
class FetchResult:
    """Yhden kaupan haun tulos."""

    site: str
    ok: bool
    products: list[Product] = field(default_factory=list)
    error: str = ""
    kept: int = 0        # suodatuksen jälkeen jääneet
    filtered_out: int = 0
