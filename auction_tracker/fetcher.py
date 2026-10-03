"""Polite page fetching with an HTTP backend and a real-Chrome backend.

* ``http``   - curl_cffi (Chrome TLS fingerprint) when installed, else requests.
* ``chrome`` - Playwright driving your installed Google Chrome with a
               persistent profile, so Cloudflare cookies survive between runs.
* ``auto``   - start with http; when a domain answers with a block/challenge,
               switch that domain to Chrome for the rest of the run.
"""

from __future__ import annotations

import logging
import os
import random
import re
import time
from urllib.parse import urlparse

log = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

CHALLENGE_MARKERS = (
    "just a moment...", "cf-chl", "challenge-platform", "attention required",
    "verify you are human", "access denied", "captcha",
)


class FetchError(RuntimeError):
    pass


def looks_blocked(status: int, html: str) -> bool:
    if status in (401, 403, 429, 503):
        return True
    head = html[:6000].lower()
    title = re.search(r"<title[^>]*>([^<]*)", head)
    if title and re.search(r"just a moment|attention required|access denied|verify|captcha|blocked", title.group(1)):
        return True                     # challenge pages can be large; trust the title
    return len(html) < 20000 and any(m in head for m in CHALLENGE_MARKERS)


class Fetcher:
    def __init__(self, cfg: dict | None = None):
        cfg = cfg or {}
        self.backend = os.environ.get("TRACKER_FETCH_BACKEND", cfg.get("backend", "auto"))
        self.delay = cfg.get("delay_seconds", [2.5, 5.0])
        self.timeout = cfg.get("timeout_seconds", 45)
        self.profile_dir = os.path.expanduser(cfg.get("chrome_profile_dir", "~/.auction-tracker-chrome"))
        self.headless = bool(cfg.get("chrome_headless", False))
        if os.environ.get("CI"):
            self.headless = True
        self._session = None
        self._pw = None
        self._ctx = None
        self._chrome_domains: set[str] = set()
        self._last: dict[str, float] = {}

    # -- lifecycle ---------------------------------------------------------
    def close(self):
        if self._ctx is not None:
            try:
                self._ctx.close()
            finally:
                self._ctx = None
        if self._pw is not None:
            self._pw.stop()
            self._pw = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- public ------------------------------------------------------------
    def get(self, url: str) -> str:
        domain = urlparse(url).netloc
        self._throttle(domain)
        use_chrome = self.backend == "chrome" or domain in self._chrome_domains
        if not use_chrome:
            status, html = self._get_http(url)
            if not looks_blocked(status, html):
                if status >= 400:
                    raise FetchError(f"HTTP {status} for {url}")
                return html
            if self.backend != "auto":
                raise FetchError(f"Blocked (HTTP {status}) at {url}; try --backend chrome")
            log.warning("%s looks blocked over HTTP; switching this domain to Chrome", domain)
            self._chrome_domains.add(domain)
        return self._get_chrome(url)

    # -- internals ---------------------------------------------------------
    def _throttle(self, domain: str):
        lo, hi = self.delay
        wait = self._last.get(domain, 0) + random.uniform(lo, hi) - time.time()
        if wait > 0:
            time.sleep(wait)
        self._last[domain] = time.time()

    def _get_http(self, url: str) -> tuple[int, str]:
        if self._session is None:
            try:
                from curl_cffi import requests as creq  # type: ignore
                self._session = creq.Session(impersonate="chrome")
                self._is_cffi = True
            except ImportError:
                import requests
                self._session = requests.Session()
                self._is_cffi = False
                self._session.headers.update({
                    "User-Agent": UA,
                    "Accept-Language": "en-MY,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                })
        last_exc = None
        for attempt in range(3):
            try:
                r = self._session.get(url, timeout=self.timeout)
                return r.status_code, r.text
            except Exception as exc:  # network hiccup
                last_exc = exc
                time.sleep(2 ** (attempt + 1))
        raise FetchError(f"Network error for {url}: {last_exc}")

    def _get_chrome(self, url: str) -> str:
        if self._ctx is None:
            try:
                from playwright.sync_api import sync_playwright  # type: ignore
            except ImportError as exc:
                raise FetchError(
                    "Chrome backend needs Playwright: pip install playwright "
                    "(it drives your installed Google Chrome)") from exc
            self._pw = sync_playwright().start()
            kwargs = dict(user_data_dir=self.profile_dir, headless=self.headless,
                          locale="en-MY", user_agent=None)
            try:
                self._ctx = self._pw.chromium.launch_persistent_context(channel="chrome", **kwargs)
            except Exception:
                log.info("Google Chrome not found; using Playwright's bundled Chromium")
                self._ctx = self._pw.chromium.launch_persistent_context(**kwargs)
        page = self._ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 1000)
            # Wait out a JS challenge (or give a human time to solve it).
            deadline = time.time() + (20 if self.headless else 90)
            html = page.content()
            while looks_blocked(200, html) and time.time() < deadline:
                page.wait_for_timeout(2000)
                html = page.content()
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            html = page.content()
            if looks_blocked(200, html):
                raise FetchError(f"Still blocked in Chrome at {url}")
            return html
        finally:
            page.close()
