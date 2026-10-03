"""Read public Telegram channels where auction agents post listings and results.

Public channels have a no-login web preview at https://t.me/s/<channel>.
(Private groups don't, and are skipped with a warning.)

What we use from each post:
  * auction listing links (bplelonglist / lelongtips / ...) -> analysed like
    any other listing
  * listing posts (building, address, size, auction price, date) -> parsed
    into listings and analysed like any other
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
import unicodedata

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


# --------------------------------------------------------------------------
# Listing posts -> Listing records
# --------------------------------------------------------------------------
PRICE_RE = re.compile(r"(?:lelong|auction|reserve)\s*price\s*:?\s*\n?\s*RM\s*([\d.,]+)\s*(k|mil|million|m)?\b", re.I)
MARKET_RE = re.compile(r"market\s*(?:value|price)\s*:?\s*RM\s*([\d.,]+)\s*(k|mil|million|m)?\b", re.I)
RENT_CLAIM_RE = re.compile(r"rental\s*:?\s*RM\s*([\d,]+)(?:\s*-\s*RM\s*([\d,]+))?", re.I)
DATE_RE = re.compile(r"(?:lelong|auction)\s*date\s*:?\s*([^\n]+)", re.I)
UNIT_BLOCK_RE = re.compile(r"^\s*unit\s*no", re.I | re.M)


def _rm(num: str, mult: str | None) -> float | None:
    try:
        v = float(num.replace(",", ""))
    except ValueError:
        return None
    m = (mult or "").lower()
    return v * (1e3 if m == "k" else 1e6 if m in ("m", "mil", "million") else 1)


def clean_text(text: str) -> str:
    """Fancy-font letters -> ASCII, drop emoji-only lines."""
    t = unicodedata.normalize("NFKC", text)
    lines = [ln.strip() for ln in t.split("\n")]
    return "\n".join(ln for ln in lines if re.search(r"[A-Za-z0-9]", ln))


def _blocks(text: str) -> list[str]:
    """One post can advertise several units; split at each 'Unit No' that
    carries its own price, keeping the shared header/footer with each."""
    starts = [m.start() for m in UNIT_BLOCK_RE.finditer(text)]
    if len(starts) < 2 or len(PRICE_RE.findall(text)) < 2:
        return [text]
    head, out = text[:starts[0]], []
    for i, st in enumerate(starts):
        body = text[st: starts[i + 1] if i + 1 < len(starts) else len(text)]
        out.append(head + body + "\n" + text[starts[-1]:])
    return out


def parse_post_listings(post: dict) -> list:
    """Agent listing posts (Yuki Cheah / Chris Pang / Trinity style) -> Listings."""
    text = clean_text(post["text"])
    if not PRICE_RE.search(text):
        return []
    ch, pid = post["channel"], post["post_id"]
    header = next((ln for ln in text.split("\n")
                   if not re.search(r"bank\s*lelong|deposit|^\W*$", ln, re.I) and len(ln) > 3), "")
    out = []
    for i, block in enumerate(_blocks(text)):
        pm = PRICE_RE.search(block)
        price = _rm(pm.group(1), pm.group(2))
        if not price or price < 30_000:
            continue
        lst = bpl.Listing(listing_id=f"tg-{ch}-{pid}" + (f"-{i + 1}" if i else ""),
                          url=f"https://t.me/{ch}/{pid}", source=f"telegram:{ch}")
        lst.reserve_price = price
        addr = re.search(r"^(?:location\s*:\s*)?((?:unit\s*no\.?\s*)?[^\n]*\b\d{5}\b[^\n]*)$", block, re.I | re.M)
        lst.address = addr.group(1).strip() if addr else ""
        unit = re.search(r"unit\s*no\.?\s*:?\s*([A-Z0-9]{1,4}(?:-[A-Z0-9]{1,4}){1,3})", block, re.I)
        if unit:
            lst.unit = unit.group(1).upper()
        lst.built_up = bpl.parse_built_up(block)
        dm = DATE_RE.search(block)
        lst.auction_date = bpl.parse_date(dm.group(1)) if dm else None
        lst.title = header[:120]
        name, _, area = header.partition("@")
        lst.area = area.strip()
        lst.building = (bpl.derive_building(lst.address, "") if lst.address else "") or name.split(",")[0].strip()
        lst.state = next((s for s in bpl.STATES if s.lower() in lst.address.lower()), "")
        for t in bpl.TYPE_WORDS + ["SOHO", "Suite", "Terrace", "Semi Detached", "Shop"]:
            if re.search(rf"\b{re.escape(t)}\b", block, re.I):
                lst.property_type = t
                break
        mv = MARKET_RE.search(block)
        if mv and _rm(mv.group(1), mv.group(2)):
            lst.flags.append(f"Agent claims market value RM{_rm(mv.group(1), mv.group(2)):,.0f} (unverified)")
        rc = RENT_CLAIM_RE.search(block)
        if rc:
            lst.flags.append(f"Agent claims rental RM{rc.group(1)}" + (f"-{rc.group(2)}" if rc.group(2) else "")
                             + " (unverified)")
        bpl.enrich(lst, block)
        lst.raw_text = block[:5000]
        out.append(lst)
    return out


def collect(conn, fetcher, channels: list[str], pages: int = 2) -> dict:
    """Fetch recent posts; return listing URLs found and counts."""
    conn.executescript(SCHEMA)
    listing_urls: list[str] = []
    post_listings: list = []
    stats = {"posts": 0, "new_posts": 0, "results": 0, "listing_posts": 0}
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
                found = parse_post_listings({**p, "channel": ch})
                stats["listing_posts"] += bool(found)
                post_listings += found
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
    return {"stats": stats, "listing_urls": list(dict.fromkeys(listing_urls)), "listings": post_listings}
