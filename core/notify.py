"""Webhook-ilmoitukset."""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import requests

from .diff import BACK_IN_STOCK, NEW, PREORDER_OPEN, PRICE_CHANGE, Event

try:
    from zoneinfo import ZoneInfo

    _HELSINKI = ZoneInfo("Europe/Helsinki")
except Exception:  # noqa: BLE001
    _HELSINKI = timezone.utc


def _now_local() -> str:
    return datetime.now(_HELSINKI).strftime("%-d.%-m. %H:%M") if os.name != "nt" \
        else datetime.now(_HELSINKI).strftime("%#d.%#m. %H:%M")

WEBHOOK_ENV = "WEBHOOK_URL"                 # ajokuittaukset (🟢 "Ajo valmis", siemennys, virheet)
WEBHOOK_ALERTS_ENV = "WEBHOOK_ALERTS_URL"   # tuotemuutokset; jos tyhjä -> WEBHOOK_URL

_KIND_META = {
    NEW: ("🆕 Uusi tuote", 0x3BA55D),
    BACK_IN_STOCK: ("✅ Takaisin varastossa", 0x57F287),
    PREORDER_OPEN: ("📦 Ennakkotilaus avautui", 0x5865F2),
    PRICE_CHANGE: ("💶 Hinta muuttui", 0xFEE75C),
}

def _price(v) -> str:
    if v is None:
        return "—"
    return f"{float(v):.2f} €".replace(".", ",")


def site_label(site: str) -> str:
    """Kohteen näyttönimi konfiguraatiosta (avain = 'key')."""
    try:
        from sites import LABELS
        return LABELS.get(site, site)
    except Exception:  # noqa: BLE001
        return site


class Notifier:
    def __init__(
        self,
        status_url: str | None = None,
        alerts_url: str | None = None,
        dry_run: bool = False,
    ):
        self.status_url = status_url or os.environ.get(WEBHOOK_ENV, "")
        self.alerts_url = (
            alerts_url or os.environ.get(WEBHOOK_ALERTS_ENV, "") or self.status_url
        )
        self.dry_run = dry_run
        if not self.dry_run and not self.status_url:
            raise RuntimeError(
                f"Ympäristömuuttuja {WEBHOOK_ENV} puuttuu (ja --dry-run ei käytössä)."
            )

    # --- matala taso ---------------------------------------------------------
    def _post(self, payload: dict, url: str) -> None:
        if self.dry_run:
            tag = "alerts" if (url == self.alerts_url != self.status_url) else "status"
            print(f"  [dry-run] webhook-viesti ({tag}):", _summarize_payload(payload))
            return
        for _ in range(5):
            r = requests.post(url, json=payload, timeout=30)
            if r.status_code == 429:
                wait = float(r.json().get("retry_after", 2))
                time.sleep(wait + 0.5)
                continue
            if r.status_code >= 300:
                raise RuntimeError(f"webhook {r.status_code}: {r.text[:300]}")
            time.sleep(0.7)  # kevyt rate-limit-suoja
            return
        raise RuntimeError("webhook: liikaa 429-vastauksia")

    # --- korkea taso -------------------------------------------------------
    def send_events(self, events: list[Event]) -> None:
        embeds = [_event_embed(e) for e in events]
        for i in range(0, len(embeds), 10):
            self._post({"embeds": embeds[i : i + 10]}, self.alerts_url)

    def send_text(self, text: str, *, alerts: bool = False) -> None:
        url = self.alerts_url if alerts else self.status_url
        for i in range(0, len(text), 1900):
            self._post({"content": text[i : i + 1900]}, url)

    def send_run_report(
        self,
        group: str,
        *,
        sites_ok: list[str],
        failures: list[tuple[str, str]],
        event_counts: dict[str, int],
        events_by_site: dict[str, int],
        seeded: list[tuple[str, int]],
        soft_failed: list[str] | None = None,
    ) -> None:
        """Lyhyt 'ajo suoritettu' -kuittaus jokaisen ajon lopuksi."""
        soft_failed = soft_failed or []
        hard = [(n, e) for n, e in failures if n not in soft_failed]
        total_changes = sum(event_counts.values())
        icon = "🟢" if not failures else "🟡"
        head = f"{icon} **Ajo valmis** · {group} · {_now_local()}"

        lines = [head]
        checked = len(sites_ok) + len(failures)
        lines.append(f"Tarkistettu {len(sites_ok)}/{checked} kohdetta.")

        if seeded:
            n = sum(c for _, c in seeded)
            lines.append(f"🔰 Ensimmäinen ajo: {n} tuotetta kirjattu "
                         f"({', '.join(site_label(s) for s, _ in seeded)}).")

        if total_changes == 0 and not seeded:
            lines.append("Ei muutoksia.")
        elif total_changes:
            bits = []
            for k in (NEW, BACK_IN_STOCK, PREORDER_OPEN, PRICE_CHANGE):
                if event_counts.get(k):
                    bits.append(f"{_KIND_META[k][0]} {event_counts[k]}")
            lines.append("**" + str(total_changes) + " muutosta:** " + " · ".join(bits))
            per_site = ", ".join(
                f"{site_label(s)} ({n})" for s, n in sorted(events_by_site.items())
            )
            if per_site:
                lines.append("Kohteet: " + per_site)

        if hard:
            lines.append("❌ Virhe: " + ", ".join(
                f"{site_label(s)} – {err[:120]}" for s, err in hard
            ))
        if soft_failed:
            lines.append("⚠️ Ei tavoitettu (ajoittain odotettua, esim. IP-esto): "
                         + ", ".join(site_label(s) for s in soft_failed))

        self.send_text("\n".join(lines))

    def send_site_summary(self, site: str, kind_counts: dict[str, int], sample: list[Event]) -> None:
        parts = [f"**{site_label(site)}** — paljon muutoksia kerralla:"]
        for k, n in kind_counts.items():
            label = _KIND_META.get(k, (k, 0))[0]
            parts.append(f"• {label}: {n} kpl")
        parts.append("")
        parts.append("Esimerkkejä:")
        for e in sample[:8]:
            parts.append(f"• {e.product.name} — <{e.product.url}>")
        self.send_text("\n".join(parts), alerts=True)


_CHANGE_TEXT = {
    NEW: "Uusi tuote valikoimassa",
    BACK_IN_STOCK: "Tuli takaisin saataville (oli loppu)",
    PREORDER_OPEN: "Ennakkotilaus aukesi",
}


def _event_embed(e: Event) -> dict:
    title, color = _KIND_META.get(e.kind, ("Muutos", 0x99AAB5))
    fields = [{"name": "Kohde", "value": site_label(e.site), "inline": True}]

    if e.kind == PRICE_CHANGE:
        delta = ""
        if e.old_price:
            diff_pct = (e.product.price - e.old_price) / e.old_price * 100
            arrow = "🔻" if diff_pct < 0 else "🔺"
            delta = f"  ({arrow}{abs(diff_pct):.0f} %)"
        fields.append({
            "name": "Hinta",
            "value": f"{_price(e.old_price)} → {_price(e.product.price)}{delta}",
            "inline": True,
        })
        change = "Hinta muuttui"
    else:
        fields.append({"name": "Hinta", "value": _price(e.product.price), "inline": True})
        change = _CHANGE_TEXT.get(e.kind, "Muutos")

    fields.append({"name": "Mikä muuttui", "value": change, "inline": False})
    if e.product.status:
        fields.append({"name": "Saatavuus", "value": e.product.status[:200], "inline": False})

    return {
        "title": title,
        "description": f"**[{e.product.name}]({e.product.url})**",
        "url": e.product.url,
        "color": color,
        "fields": fields,
        "footer": {"text": f"{site_label(e.site)} · vahti"},
    }


def _summarize_payload(payload: dict) -> str:
    if "content" in payload:
        return payload["content"][:400]
    embeds = payload.get("embeds", [])
    return " | ".join(
        f"{em.get('title','')}: {em.get('description','')[:80]}" for em in embeds
    )
