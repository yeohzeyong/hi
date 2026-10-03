"""Telegram alerts for new top-grade deals (optional).

Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID (GitHub secrets or env vars).
Each listing is announced once per reserve price, so a price cut on a
re-auction triggers a fresh alert.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

import requests

from .scoring import GRADE_ORDER

log = logging.getLogger(__name__)


def format_message(e: dict) -> str:
    l, f, b = e["listing"], e["finance"], e["max_bid"]
    st = e.get("station")
    lines = [
        f"🏠 [{e['grade']}] {l['building'] or l['title']} - {l['area_label']}",
        f"Reserve RM{l['reserve_price']:,.0f} · {l['built_up']:,.0f} sqft · auction {l['auction_date'] or 'TBC'}",
        f"Rent ~RM{e['rent_estimate'] or 0:,} vs cost RM{f.get('monthly_cost', 0):,}/mth ({f.get('rent_cover', 0):.2f}x)",
    ]
    if f.get("discount") is not None:
        lines.append(f"{f['discount']:.0%} below market (~RM{e['market_value']:,})")
    if st:
        lines.append(f"{st['walk_m']} m to {st['type']} {st['name']}")
    if l.get("dual_key"):
        lines.append("Dual key ✅")
    v = e.get("verdict") or {}
    if v:
        lines.append(f"➡️ {v['action']}: {v['text']}")
    elif b.get("max_bid"):
        lines.append(f"Walk-away bid: RM{b['max_bid']:,}")
    lines.append(l["url"])
    return "\n".join(lines)


def send_test() -> str:
    """Send a hello message so you know alerts are wired up correctly."""
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID secrets are not set")
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat, "text": "✅ Auction tracker connected. New A-grade deals will arrive here."},
                      timeout=20)
    if not r.ok:
        raise RuntimeError(f"Telegram refused the message: {r.status_code} {r.text[:200]}")
    return "sent"


def notify(conn, results: list[dict], min_grade: str = "A") -> int:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    sent = 0
    for e in results:
        if e["status"] != "ok" or GRADE_ORDER[e["grade"]] < GRADE_ORDER[min_grade]:
            continue
        l = e["listing"]
        if conn.execute("SELECT 1 FROM notified WHERE listing_id=? AND reserve_price=?",
                        (l["listing_id"], l["reserve_price"])).fetchone():
            continue
        msg = format_message(e)
        if token and chat:
            try:
                requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                              json={"chat_id": chat, "text": msg, "disable_web_page_preview": True},
                              timeout=20).raise_for_status()
            except Exception as exc:
                log.warning("telegram failed: %s", exc)
                continue
        else:
            log.info("NEW DEAL (no Telegram configured):\n%s", msg)
        conn.execute("INSERT OR REPLACE INTO notified VALUES (?,?,?,?)",
                     (l["listing_id"], e["grade"], l["reserve_price"], datetime.now().isoformat(timespec="seconds")))
        sent += 1
    conn.commit()
    return sent
