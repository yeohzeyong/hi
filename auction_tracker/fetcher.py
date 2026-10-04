"""Polite page fetching with an HTTP backend and a real-Chrome backend.

* ``http``   - curl_cffi (Chrome TLS fingerprint) when installed, else requests.
* ``chrome`` - Playwright driving your installed Google Chrome with a
               persistent profile, so Cloudflare cookies survive between runs.
* ``auto``   - start with http; when a domain answers with a block/challenge,
               switch that domain to Chrome for the rest of the run.
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
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
    low = html[:60000].lower()
    if "performing security verification" in low or "verify you are human" in low and "cloudflare" in low:
        return True
    head = low[:6000]
    title = re.search(r"<title[^>]*>([^<]*)", low)
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
        # Cloud: give up on a blocking site fast. Your PC: allow time for you
        # to tick the "verify you are human" box.
        self.max_blocks = 2 if self.headless else 6
        self._session = None
        self._pw = None
        self._ctx = None
        self._browser = None
        self._chrome_proc = None
        self._reopens = 0
        self._chrome_domains: set[str] = set()
        self._blocked: dict[str, int] = {}      # domain -> hard blocks this run
        self._last: dict[str, float] = {}

    # -- lifecycle ---------------------------------------------------------
    def close(self):
        if self._ctx is not None and self._chrome_proc is None:
            try:
                self._ctx.close()
            except Exception:
                pass
        self._ctx = None
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._pw is not None:
            self._pw.stop()
            self._pw = None
        if self._chrome_proc is not None:
            self._chrome_proc.terminate()
            self._chrome_proc = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- public ------------------------------------------------------------
    def get(self, url: str) -> str:
        domain = urlparse(url).netloc
        if self._blocked.get(domain, 0) >= self.max_blocks:
            # Cloud servers get a hard "no" from some portals; don't burn
            # half a minute per request finding that out again.
            raise FetchError(f"Skipped {domain}: blocked earlier this run")
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

    def _start_real_chrome(self) -> bool:
        """Start your normal Google Chrome (no automation flags) and attach to
        it. Cloudflare's "verify you are human" check passes for a normally
        started Chrome but loops forever for a Playwright-launched one."""
        exe = find_chrome()
        if not exe:
            return False
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        os.makedirs(self.profile_dir, exist_ok=True)
        self._chrome_proc = subprocess.Popen(
            [exe, f"--remote-debugging-port={port}", f"--user-data-dir={self.profile_dir}",
             "--no-first-run", "--no-default-browser-check", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        endpoint = f"http://127.0.0.1:{port}"
        for _ in range(60):
            try:
                with urllib.request.urlopen(endpoint + "/json/version", timeout=1) as r:
                    json.load(r)
                break
            except Exception:
                time.sleep(0.5)
        else:
            log.warning("Chrome did not open its debugging port; falling back")
            self._chrome_proc.terminate()
            self._chrome_proc = None
            return False
        self._browser = self._pw.chromium.connect_over_cdp(endpoint)
        self._ctx = self._browser.contexts[0] if self._browser.contexts else self._browser.new_context()
        log.info("Using your Google Chrome (%s)", exe)
        return True

    def _get_chrome(self, url: str) -> str:
        domain = urlparse(url).netloc
        if self._ctx is None:
            try:
                from playwright.sync_api import sync_playwright  # type: ignore
            except ImportError as exc:
                raise FetchError(
                    "Chrome backend needs Playwright: pip install playwright "
                    "(it drives your installed Google Chrome)") from exc
            self._pw = sync_playwright().start()
            if not self.headless and self._start_real_chrome():
                pass
            else:
                kwargs = dict(user_data_dir=self.profile_dir, headless=self.headless, locale="en-MY",
                              args=["--disable-blink-features=AutomationControlled"],
                              ignore_default_args=["--enable-automation"])
                try:
                    self._ctx = self._pw.chromium.launch_persistent_context(channel="chrome", **kwargs)
                except Exception:
                    log.info("Google Chrome not found; using Playwright's bundled Chromium")
                    self._ctx = self._pw.chromium.launch_persistent_context(**kwargs)
        try:
            page = self._ctx.new_page()
        except Exception as exc:
            if ("closed" not in str(exc).lower() and "target" not in str(exc).lower()) or self._reopens >= 2:
                raise
            self._reopens += 1
            log.warning("Chrome window was closed - reopening it")
            self.close()
            return self._get_chrome(url)
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
                self._blocked[domain] = self._blocked.get(domain, 0) + 1
                if self._blocked[domain] == self.max_blocks:
                    log.error("%s blocks this machine - skipping it for the rest of the run. "
                              "Run run_local.bat on your PC to fetch its prices.", domain)
                raise FetchError(f"Still blocked in Chrome at {url}")
            return html
        finally:
            page.close()


def find_chrome() -> str | None:
    """Locate an installed Google Chrome (or Chromium) executable."""
    env = os.environ.get("CHROME_PATH")
    if env and os.path.exists(env):
        return env
    cands = []
    if sys.platform.startswith("win"):
        for base in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")):
            if base:
                cands.append(os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"))
    elif sys.platform == "darwin":
        cands.append("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    for c in cands:
        if os.path.exists(c):
            return c
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        p = shutil.which(name)
        if p:
            return p
    return None
