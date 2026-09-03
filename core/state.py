"""state.json luku ja tallennus.

Rakenne:
{
  "_meta": {"updated": "2026-09-02T12:00:00Z"},
  "sites": {
    "<kohde-key>": {
      "seeded": true,
      "products": {
        "<key>": {"name","url","price","in_stock","preorder","status",
                   "first_seen","last_seen"}
      }
    }
  }
}
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

STATE_PATH = os.environ.get("MONITOR_STATE_PATH", "state.json")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path: str = STATE_PATH) -> dict:
    if not os.path.exists(path):
        return {"_meta": {}, "sites": {}}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("_meta", {})
    data.setdefault("sites", {})
    return data


def save(data: dict, path: str = STATE_PATH) -> None:
    data.setdefault("_meta", {})["updated"] = now_iso()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, path)


def site_products(data: dict, site: str) -> dict:
    return data["sites"].get(site, {}).get("products", {})


def site_seeded(data: dict, site: str) -> bool:
    return bool(data["sites"].get(site, {}).get("seeded"))
