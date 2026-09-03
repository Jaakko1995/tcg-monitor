"""Seurattavien kohteiden konfiguraatio.

Kohteiden nimet ja osoitteet EIVÄT ole versionhallinnassa (julkinen repo).
Lataus järjestyksessä:
  1) ympäristömuuttuja MONITOR_CONFIG_B64  (base64-koodattu JSON) — GitHub Actions
  2) tiedosto config.json                  — paikallinen ajo
  3) config.example.json                   — geneerinen malli (vain rakenne)
"""
from __future__ import annotations

import base64
import json
import os
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parent.parent


def load() -> dict:
    b64 = os.environ.get("MONITOR_CONFIG_B64")
    if b64:
        return json.loads(base64.b64decode(b64))
    for name in ("config.json", "config.example.json"):
        p = _ROOT / name
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    raise RuntimeError(
        "Konfiguraatiota ei löytynyt: aseta MONITOR_CONFIG_B64 tai luo config.json"
    )
