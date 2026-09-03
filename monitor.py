#!/usr/bin/env python3
"""vahti: hakee kohteiden tuotteet, vertaa edelliseen tilaan ja
lähettää muutokset webhookiin.

Käyttö:
  py monitor.py --group light            # nopeat HTTP-kaupat
  py monitor.py --group heavy            # Playwright-kaupat
  py monitor.py --site <key> --dry-run
  py monitor.py --group all --dry-run    # näytä mitä löytyy, älä lähetä/tallenna
"""
from __future__ import annotations

import argparse
import sys
import traceback

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass

from core import diff, state
from core.filters import keep_product
from core.models import FetchResult
from core.notify import Notifier, site_label
from sites import select

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

EVENT_CAP_PER_SITE = 25  # tätä isommat muutosmäärät -> koontiviesti


def run_site(site) -> FetchResult:
    try:
        raw = site.fetch()
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        return FetchResult(site.name, ok=False, error=str(e))

    kept: list = []
    filtered = 0
    for p in raw:
        if keep_product(
            p,
            require_any=site.require_any,
            exclude_any=site.exclude_any,
        ):
            kept.append(p)
        else:
            filtered += 1

    # dedup avaimella
    dedup = {p.key: p for p in kept}
    return FetchResult(
        site.name, ok=True, products=list(dedup.values()),
        kept=len(dedup), filtered_out=filtered,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="vahti")
    ap.add_argument("--group", default="all",
                    help="ryhmä konfiguraatiosta (esim. light / browser) tai 'all'")
    ap.add_argument("--site", action="append", dest="sites", metavar="NIMI",
                    help="aja vain nimetty kohde (voi toistaa)")
    ap.add_argument("--dry-run", action="store_true",
                    help="älä lähetä webhookiin äläkä tallenna tilaa")
    ap.add_argument("--state", default=state.STATE_PATH, help="state.json polku")
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--no-heartbeat", action="store_true",
                    help="älä lähetä 'ajo valmis' -kuittausta")
    ap.add_argument("--test-message", action="store_true",
                    help="lähetä testiviesti webhookiin ja lopeta")
    args = ap.parse_args(argv)

    if args.test_message:
        n = Notifier(dry_run=args.dry_run)
        n.send_text("✅ Testiviesti — ajokuittausten kanava (WEBHOOK_URL).")
        if n.alerts_url and n.alerts_url != n.status_url:
            n.send_text("✅ Testiviesti — tuotemuutosten kanava (WEBHOOK_ALERTS_URL).",
                        alerts=True)
            print("Testiviestit lähetetty molempiin kanaviin.")
        else:
            print("Testiviesti lähetetty (yksi kanava käytössä).")
        return 0

    sites = select(args.group, args.sites)
    if not sites:
        print("Ei kauppoja valittuna.", file=sys.stderr)
        return 2

    data = state.load(args.state)
    notifier = Notifier(dry_run=args.dry_run)

    all_events: list[diff.Event] = []
    seeded_now: list[tuple[str, int]] = []
    failures: list[tuple[str, str]] = []
    summaries: list[tuple[str, dict, list]] = []
    sites_ok: list[str] = []
    events_by_site: dict[str, int] = {}
    event_counts: dict[str, int] = {}

    hard_failures: list[str] = []

    for site in sites:
        print(f"\n=== {site_label(site.name)} ({site.group}) ===")
        res = run_site(site)
        if not res.ok:
            tag = "(best-effort)" if site.best_effort else ""
            print(f"  VIRHE {tag}: {res.error}")
            failures.append((site.name, res.error))
            if not site.best_effort:
                hard_failures.append(site.name)
            continue

        print(f"  tuotteita: {res.kept} (suodatettu pois {res.filtered_out})")

        # 0 tuotetta = haku ei oikeasti onnistunut (esto/rakennemuutos). Ei siemennetä
        # tyhjää eikä hälytetä; raportoidaan virheenä.
        if not res.products:
            msg = "0 tuotetta (mahdollinen esto tai rakennemuutos)"
            print(f"  VIRHE {'(best-effort)' if site.best_effort else ''}: {msg}")
            failures.append((site.name, msg))
            if not site.best_effort:
                hard_failures.append(site.name)
            continue

        if args.verbose:
            for p in res.products[:12]:
                flag = "IN " if p.in_stock else ("PRE" if p.preorder else "-  ")
                print(f"    [{flag}] {p.name[:58]:58}  {str(p.price):>7}  {p.status[:28]}")

        was_seeded = state.site_seeded(data, site.name)
        old = state.site_products(data, site.name)

        # Turvatarkistus: jos aiemmin oli paljon tuotteita ja nyt melkein ei yhtään,
        # parseri on todennäköisesti rikki (sivun rakenne muuttui). Ei päivitetä tilaa
        # eikä hälytetä -> ongelma näkyy 🟡-kuittauksessa.
        if was_seeded and len(old) >= 10 and res.kept < max(3, len(old) * 0.25):
            msg = f"tuotemäärä romahti {len(old)} → {res.kept}, parseri ehkä rikki – ohitettu"
            print(f"  VAROITUS: {msg}")
            failures.append((site.name, msg))
            if not site.best_effort:
                hard_failures.append(site.name)
            continue

        sites_ok.append(site.name)
        events, new_products = diff.diff_site(
            site.name, old, res.products, seeded=was_seeded,
        )

        data["sites"][site.name] = {"seeded": True, "products": new_products}

        if not was_seeded:
            seeded_now.append((site.name, len(new_products)))
            print(f"  -> siemennetty ({len(new_products)} tuotetta), ei hälytyksiä")
            continue

        if events:
            events_by_site[site.name] = len(events)
            for e in events:
                event_counts[e.kind] = event_counts.get(e.kind, 0) + 1

        if len(events) > EVENT_CAP_PER_SITE:
            counts: dict[str, int] = {}
            for e in events:
                counts[e.kind] = counts.get(e.kind, 0) + 1
            summaries.append((site.name, counts, events))
            print(f"  -> {len(events)} muutosta -> koontiviesti")
        else:
            all_events.extend(events)
            for e in events:
                print(f"  * {e.kind}: {e.product.name[:55]}")

    # --- ilmoitukset -------------------------------------------------------
    if seeded_now and not args.dry_run:
        total = sum(n for _, n in seeded_now)
        lines = ["🔔 **vahti käynnistetty**", ""]
        lines += [f"• {site_label(n)}: {c} tuotetta kirjattu" for n, c in seeded_now]
        lines += ["", f"Yhteensä {total}. Seuraavista ajoista lähtien ilmoitetaan muutokset."]
        notifier.send_text("\n".join(lines))
    elif seeded_now:
        print(f"\n[dry-run] olisi siemennetty: {seeded_now}")

    for name, counts, events in summaries:
        notifier.send_site_summary(name, counts, events)

    if all_events:
        all_events.sort(key=lambda e: (e.site, e.kind))
        notifier.send_events(all_events)
        print(f"\nLähetetty {len(all_events)} ilmoitusta.")
    else:
        print("\nEi uusia muutoksia.")

    # --- ajokuittaus (heartbeat) ----------------------------------------
    if not args.no_heartbeat and not args.dry_run:
        soft_failed = [n for n, _ in failures if n not in hard_failures]
        notifier.send_run_report(
            args.group,
            sites_ok=sites_ok,
            failures=failures,
            event_counts=event_counts,
            events_by_site=events_by_site,
            seeded=seeded_now,
            soft_failed=soft_failed,
        )
    elif args.dry_run and failures:
        print(f"\n[dry-run] epäonnistui: {failures}")

    # --- tallennus -------------------------------------------------------
    if not args.dry_run:
        state.save(data, args.state)
        print(f"Tila tallennettu: {args.state}")

    # Poistumiskoodi: 1 vain jos "kova" kohde hajosi. Best-effort-estot
    # (Cloudflare datakeskus-IP:lle) raportoidaan webhookin 🟡-kuittauksessa eikä workflow'n
    # tarvitse mennä punaiseksi. webhookin täysvika nostaa poikkeuksen -> nonzero jo sielä.
    if hard_failures:
        print(f"\nKovia virheitä: {hard_failures}")
        return 1
    if failures:
        print(f"\nBest-effort-kaupat pois pelistä (ei kaada ajoa): "
              f"{[n for n, _ in failures]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
