"""Read public Telegram channels where auction agents post listings and results.

Public channels have a no-login web preview at https://t.me/s/<channel>.
(Private groups don't, and are skipped with a warning.)

What we use from each post:
  * auction listing links (bplelonglist / lelongtips / ...) -> analysed like
    any other listing
  * posts that look like auction RESULTS ("sold", "terjual", RM amounts) ->
    written to data/telegram_inbox.csv for you to confirm. They are NOT fed
    into valuations automatically - copy confirmed rows into
    data/auction_results.csv.
Every post is stored in the database so the parser can be improved later.
"""

from __future__ import annotations

import csv
import json
import logging
import re

from bs4 import BeautifulSoup

from . import bpl
from .config import DATA_DIR

log = logging.getLogger(__name__)

INBOX_FILE = DATA_DIR / "telegram_inbox.csv"
SCHEMA = """
CREATE TABLE IF NOT EXISTS telegram_posts (
    channel TEXT, post_id INTEGER, posted_at TEXT, text TEXT, links TEXT,
    PRIMARY KEY (channel, post_id)
);
"""
RESULT_RE = re.compile(r"\b(sold|terjual|berjaya\s+dijual|successful(?:ly)?\s+(?:sold|bid|bidder)|"
                       r"auction\s+result|keputusan\s+lelong|hammer(?:ed)?\s+(?:at|price))\b", re.I)
MONEY_RE = re.compile(r"RM\s*([\d,]+(?:\.\d+)?)\s*([kKmM])?\b")


def channel_name(ref: str) -> str:
    """'t.me/MyPropertyInvest/3' or 'https://t.me/s/x' -> 'MyPropertyInvest' / 'x'."""
    ref = re.sub(r"^(https?://)?(www\.)?t\.me/(s/)?", "", ref.strip())
    return ref.split("/")[0].split("?")[0].lstrip("@")


def parse_page(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    posts = []
    for msg in soup.select("div.tgme_widget_message[data-post]"):
        ch, _, pid = msg["data-post"].rpartition("/")
        if not pid.isdigit():
            continue
        body = msg.select_one(".tgme_widget_message_text")
        text = body.get_text("\n", strip=True) if body else ""
        links = [a["href"] for a in (body.find_all("a", href=True) if body else [])]
        t = msg.select_one("time[datetime]")
        posts.append({"channel": ch, "post_id": int(pid), "posted_at": t["datetime"] if t else "",
                      "text": text, "links": links})
    return posts


def money_values(text: str) -> list[float]:
    out = []
    for m in MONEY_RE.finditer(text):
        v = float(m.group(1).replace(",", "")) * {"k": 1e3, "m": 1e6}.get((m.group(2) or "").lower(), 1)
        if 30_000 <= v <= 20_000_000:          # property-sized amounts only
            out.append(v)
    return out


def looks_like_result(text: str) -> bool:
    return bool(RESULT_RE.search(text)) and bool(money_values(text))


def collect(conn, fetcher, channels: list[str], pages: int = 2) -> dict:
    """Fetch recent posts; return listing URLs found and counts."""
    conn.executescript(SCHEMA)
    listing_urls: list[str] = []
    stats = {"posts": 0, "new_posts": 0, "results": 0}
    inbox_rows = []
    for ref in channels:
        ch = channel_name(ref)
        before = None
        for _ in range(pages):
            url = f"https://t.me/s/{ch}" + (f"?before={before}" if before else "")
            try:
                posts = parse_page(fetcher.get(url))
            except Exception as exc:
                log.warning("telegram %s failed: %s", ch, exc)
                break
            if not posts:
                log.warning("telegram %s: no public posts (private group or no web preview)", ch)
                break
            for p in posts:
                stats["posts"] += 1
                cur = conn.execute("INSERT OR IGNORE INTO telegram_posts VALUES (?,?,?,?,?)",
                                   (ch, p["post_id"], p["posted_at"], p["text"], json.dumps(p["links"])))
                is_new = cur.rowcount > 0
                stats["new_posts"] += is_new
                blob = p["text"] + " " + " ".join(p["links"])
                listing_urls += bpl.extract_listing_links(blob)
                if is_new and looks_like_result(p["text"]):
                    stats["results"] += 1
                    inbox_rows.append([p["posted_at"][:10], ch, f"https://t.me/{ch}/{p['post_id']}",
                                       " / ".join(f"{v:,.0f}" for v in money_values(p["text"])),
                                       re.sub(r"\s+", " ", p["text"])[:400]])
            before = min(p["post_id"] for p in posts)
            if before <= 1:
                break
    conn.commit()
    if inbox_rows:
        new_file = not INBOX_FILE.exists()
        with open(INBOX_FILE, "a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            if new_file:
                w.writerow(["posted", "channel", "post", "rm_amounts", "text"])
            w.writerows(inbox_rows)
    stats["listing_links"] = len(set(listing_urls))
    log.info("telegram: %s", stats)
    return {"stats": stats, "listing_urls": list(dict.fromkeys(listing_urls))}
