"""Jaettu HTTP-sessio requests-pohjaisille hakijoille."""
from __future__ import annotations

import time

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

_session: requests.Session | None = None


def session() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        s.headers.update(
            {
                "User-Agent": UA,
                "Accept-Language": "fi-FI,fi;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "application/json;q=0.9,image/avif,image/webp,*/*;q=0.8"
                ),
                "Accept-Encoding": "gzip, deflate",
                "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            }
        )
        _session = s
    return _session


def get(url: str, *, params=None, timeout: int = 30, retries: int = 3, **kw):
    last = None
    for attempt in range(retries):
        try:
            r = session().get(url, params=params, timeout=timeout, **kw)
            # 403 = usein hetkellinen rate-limit/WAF -> yritetään uudelleen pidemmällä tauolla
            if r.status_code in (403, 429, 500, 502, 503, 504):
                last = RuntimeError(f"{r.status_code} {url}")
                time.sleep((5 if r.status_code == 403 else 2) * (attempt + 1))
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as e:  # noqa: PERF203
            last = e
            time.sleep(2 * (attempt + 1))
    raise last  # type: ignore[misc]
