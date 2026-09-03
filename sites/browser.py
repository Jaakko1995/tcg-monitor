"""Playwright-pohjainen renderöinti SPA- ja Cloudflare-sivuille."""
from __future__ import annotations

import contextlib
import time
from collections.abc import Iterator

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

_BLOCK_TYPES = {"image", "media", "font"}

# Cloudflare-välisivun otsikoita (myös suomeksi)
_CHALLENGE_TITLES = (
    "just a moment", "pieni hetki", "odota hetki", "checking your browser",
    "attention required", "one moment",
)


def _looks_like_challenge(page) -> bool:
    try:
        t = (page.title() or "").lower()
    except Exception:  # noqa: BLE001
        return False
    return any(s in t for s in _CHALLENGE_TITLES)


def wait_out_challenge(page, *, total_ms: int = 25000, step_ms: int = 4000) -> None:
    """Odota että Cloudflaren JS-haaste ratkeaa itsestään."""
    waited = 0
    while waited < total_ms and _looks_like_challenge(page):
        page.wait_for_timeout(step_ms)
        waited += step_ms
        with contextlib.suppress(Exception):
            page.wait_for_load_state("domcontentloaded")


@contextlib.contextmanager
def browser_page() -> Iterator["Page"]:  # type: ignore[name-defined]
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = browser.new_context(
            user_agent=UA,
            locale="fi-FI",
            timezone_id="Europe/Helsinki",
            viewport={"width": 1366, "height": 900},
            extra_http_headers={"Accept-Language": "fi-FI,fi;q=0.9,en;q=0.8"},
        )
        context.set_default_timeout(45000)

        def _route(route):
            if route.request.resource_type in _BLOCK_TYPES:
                return route.abort()
            return route.continue_()

        context.route("**/*", _route)
        page = context.new_page()
        try:
            yield page
        finally:
            with contextlib.suppress(Exception):
                context.close()
            with contextlib.suppress(Exception):
                browser.close()


def render(
    page,
    url: str,
    *,
    wait_selector: str | None = None,
    wait_timeout: int = 20000,
    scrolls: int = 4,
    settle_ms: int = 1200,
    challenge_wait_ms: int = 6000,
) -> str:
    """Lataa sivu, odota sisältöä, vieritä alas, palauta HTML."""
    page.goto(url, wait_until="domcontentloaded")

    # Cloudflare-välisivu (esim. "Pieni hetki..."): odota että se ratkeaa
    if _looks_like_challenge(page):
        wait_out_challenge(page, total_ms=max(challenge_wait_ms, 20000))

    if wait_selector:
        with contextlib.suppress(Exception):
            page.wait_for_selector(wait_selector, timeout=wait_timeout)

    last_height = 0
    for _ in range(max(scrolls, 0)):
        page.mouse.wheel(0, 20000)
        page.wait_for_timeout(settle_ms)
        height = page.evaluate("document.body.scrollHeight")
        if height == last_height:
            break
        last_height = height

    return page.content()
