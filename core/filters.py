"""Tuotesuodatus require/exclude-avainsanoilla (avainsanat tulevat konfiguraatiosta)."""
from __future__ import annotations

import re
import unicodedata

from .models import Product


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower()


def matches_any(text: str, needles: list[str]) -> bool:
    t = _norm(text)
    return any(_norm(n) in t for n in needles)


def keep_product(
    p: Product,
    *,
    require_any: list[str] | None = None,
    exclude_any: list[str] | None = None,
    extra_haystack: str = "",
) -> bool:
    """Palauttaa True jos tuote pidetään."""
    hay = f"{p.name} {p.status} {extra_haystack}"
    if exclude_any and matches_any(hay, exclude_any):
        return False
    if require_any and not matches_any(hay, require_any):
        return False
    return True
