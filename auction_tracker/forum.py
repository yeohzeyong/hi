"""What owners and tenants say about a building on Lowyat PropertyTalk.

For each building: find its Lowyat threads (via a web search restricted to
forum.lowyat.net), read the first and latest pages, and keep the posts that
talk about things that matter to a landlord - water, lifts, security,
management, flooding, parking, rental demand, defects. Each kept comment is
tagged by topic and tone and linked to its thread, so you can read it in
context. Results are cached in data/forum/<building>.json for 30 days.

Runs on your PC (with run_local.bat), like the portal prices: search engines
and Lowyat tend to block cloud servers.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

from bs4 import BeautifulSoup

from .config import DATA_DIR

log = logging.getLogger(__name__)

FORUM_DIR = DATA_DIR / "forum"
TOPIC_RE = re.compile(r"https?://forum\.lowyat\.net/topic/(\d+)")

TOPICS = {
    "water": r"water|paip|pipe|leak|bocor|seepage",
    "lifts": r"\blifts?\b|elevator",
    "security": r"security|guard|theft|stolen|curi|break[- ]in|burglar|access card",
    "management": r"\bjmb\b|\bmc\b|management|maintenance fee|sinking fund|service charge",
    "flood": r"flood|banjir",
    "parking": r"parking|car ?park|petak",
    "rental demand": r"tenant|rent(?:al|ed|ing)?\b|airbnb|occupancy|vacan",
    "defects": r"defect|crack|mould|mold|termite|renovat",
    "traffic/access": r"traffic|jam\b|congest|\bmrt\b|\blrt\b|monorail|highway",
}
NEGATIVE = r"problem|issue|broken|rosak|bad|worst|terrible|dirty|kotor|leak|flood|theft|stolen|slow|rude|" \
           r"poor|complain|avoid|regret|not worth|expensive|haunted|smell|noisy|always down|frequent"
POSITIVE = r"\bgood\b|nice|clean|convenient|worth|recommend|well[- ]maintained|happy|easy to rent|" \
           r"high demand|love|great|strategic|value for money"


def _file(key: str) -> Path:
    return FORUM_DIR / (re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-") + ".json")


def load(key: str) -> dict | None:
    f = _file(key)
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    except (OSError, json.JSONDecodeError):
        return None


def is_fresh(key: str, max_age_days: int = 30) -> bool:
    d = load(key)
    if not d or not d.get("fetched_at"):
        return False
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(d["fetched_at"])).days
    return age <= max_age_days


def save(key: str, data: dict):
    FORUM_DIR.mkdir(parents=True, exist_ok=True)
    data = {**data, "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    _file(key).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------------------
# Finding threads
# ---------------------------------------------------------------------------
def search_urls(name: str) -> list[str]:
    q = quote_plus(f'site:forum.lowyat.net "{name}"')
    return [f"https://html.duckduckgo.com/html/?q={q}", f"https://www.bing.com/search?q={q}"]


def topic_links(html: str) -> list[str]:
    """Lowyat topic URLs from a search results page (handles redirect links)."""
    out, seen = [], set()
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "uddg=" in href:                                  # DuckDuckGo redirect
            href = unquote(parse_qs(urlparse(href).query).get("uddg", [""])[0])
        m = TOPIC_RE.search(href)
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            out.append(f"https://forum.lowyat.net/topic/{m.group(1)}")
    return out


# ---------------------------------------------------------------------------
# Reading a thread
# ---------------------------------------------------------------------------
DATE_RE = re.compile(r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4})")


def parse_thread(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.get_text(" ", strip=True) if soup.title else "").replace(" - Lowyat.NET", "").strip()
    posts = []
    bodies = soup.select("div.postcolor, div.post_body, div.post-content, div[id^=post-]")
    for b in bodies:
        for q in b.select("div.quotemain, div.quotetop, blockquote"):
            q.decompose()                                     # skip quoted text
        text = re.sub(r"\s+", " ", b.get_text(" ", strip=True))
        if len(text) < 25:
            continue
        date = None
        row = b.find_parent("table") or b.parent
        if row:
            m = DATE_RE.search(row.get_text(" ", strip=True))
            date = m.group(1) if m else None
        posts.append({"text": text, "date": date})
    pages = [int(x) for x in re.findall(r"/topic/\d+/\+(\d+)", html)]
    return {"title": title, "url": url, "posts": posts, "last_offset": max(pages) if pages else 0}


def classify(text: str) -> tuple[list[str], str]:
    low = text.lower()
    topics = [t for t, rx in TOPICS.items() if re.search(rx, low)]
    neg, pos = len(re.findall(NEGATIVE, low)), len(re.findall(POSITIVE, low))
    tone = "negative" if neg > pos else "positive" if pos > neg else "neutral"
    return topics, tone


def _snippet(text: str, topics: list[str], limit: int = 320) -> str:
    """Centre the excerpt on the first topic keyword."""
    low = text.lower()
    pos = min([m.start() for t in topics for m in [re.search(TOPICS[t], low)] if m] or [0])
    start = max(0, pos - 100)
    s = text[start:start + limit]
    return ("…" if start else "") + s + ("…" if start + limit < len(text) else "")


def collect(fetcher, building: str, max_threads: int = 3, max_snippets: int = 12) -> dict:
    """Search, read and summarise Lowyat discussion about one building."""
    from .portals import search_names
    names = search_names(building) or [building]
    threads: list[str] = []
    for name in names:
        for url in search_urls(name):
            try:
                threads = topic_links(fetcher.get(url))
            except Exception as exc:
                log.info("forum search failed (%s): %s", url.split("/")[2], exc)
                continue
            if threads:
                break
        if threads:
            break
    snippets, titles = [], []
    for t in threads[:max_threads]:
        try:
            first = parse_thread(fetcher.get(t), t)
        except Exception as exc:
            log.info("lowyat thread failed %s: %s", t, exc)
            continue
        titles.append({"title": first["title"], "url": t})
        posts = first["posts"]
        if first["last_offset"]:                              # newest page = current situation
            try:
                last = parse_thread(fetcher.get(f"{t}/+{first['last_offset']}"), t)
                posts = last["posts"] + posts
            except Exception:
                pass
        for p in posts:
            topics, tone = classify(p["text"])
            if not topics:
                continue
            snippets.append({"text": _snippet(p["text"], topics), "date": p["date"], "topics": topics,
                             "tone": tone, "url": t, "thread": first["title"]})
    # Keep the most useful: concerns first (they change decisions), then praise.
    order = {"negative": 0, "positive": 1, "neutral": 2}
    snippets.sort(key=lambda s: order[s["tone"]])
    seen, kept = set(), []
    for s in snippets:
        k = s["text"][:80]
        if k not in seen:
            seen.add(k)
            kept.append(s)
    return {"building": building, "threads": titles, "snippets": kept[:max_snippets]}


def summary(data: dict | None) -> dict:
    """Counts per topic of negative comments - used to flag recurring issues."""
    if not data:
        return {"found": False}
    neg: dict[str, int] = {}
    for s in data.get("snippets", []):
        if s["tone"] == "negative":
            for t in s["topics"]:
                neg[t] = neg.get(t, 0) + 1
    return {"found": bool(data.get("threads")), "threads": len(data.get("threads", [])),
            "comments": len(data.get("snippets", [])), "negative_topics": neg}
