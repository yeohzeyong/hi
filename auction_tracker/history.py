"""Learn from past auctions stored in the database.

* Unit history  - the same unit relisted with a lower reserve each round
                  (typically -10% per failed auction) => motivated seller.
* Building stats - how often a building shows up at auction, at what psf, and
                  how often units fail to sell (oversupply / weak demand).
Outcome inference (best-effort, the site does not publish results):
  relisted later           -> previous round UNSOLD
  vanished before the date -> WITHDRAWN (borrower settled / postponed)
  auction passed, never relisted within 120 days -> LIKELY SOLD
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, timedelta


def _events(conn):
    """One event per (fingerprint, auction_date)."""
    rows = conn.execute("""
        SELECT l.listing_id, l.fingerprint, l.building_key, l.area_label, l.built_up, l.last_seen,
               o.auction_date, o.reserve_price, o.seen_date
        FROM observations o JOIN listings l USING (listing_id)
        WHERE o.auction_date IS NOT NULL AND o.reserve_price IS NOT NULL
        ORDER BY o.seen_date""").fetchall()
    ev: dict[tuple, dict] = {}
    for r in rows:
        key = (r["fingerprint"], r["auction_date"])
        e = ev.setdefault(key, {"fingerprint": r["fingerprint"], "building_key": r["building_key"],
                                "area_label": r["area_label"], "built_up": r["built_up"],
                                "auction_date": r["auction_date"], "reserve_price": r["reserve_price"],
                                "last_seen": r["seen_date"]})
        e["reserve_price"] = r["reserve_price"]          # latest seen price for that date
        e["last_seen"] = max(e["last_seen"], r["seen_date"])
    return list(ev.values())


def infer_outcomes(events: list[dict], today: date | None = None) -> list[dict]:
    today = today or date.today()
    by_fp = defaultdict(list)
    for e in events:
        by_fp[e["fingerprint"]].append(e)
    for evs in by_fp.values():
        evs.sort(key=lambda e: e["auction_date"])
        for i, e in enumerate(evs):
            ad = date.fromisoformat(e["auction_date"])
            if i + 1 < len(evs):
                e["outcome"] = "unsold"
            elif ad >= today:
                e["outcome"] = "upcoming"
            elif date.fromisoformat(e["last_seen"]) < ad - timedelta(days=2):
                e["outcome"] = "withdrawn"
            elif (today - ad).days > 120:
                e["outcome"] = "likely_sold"
            else:
                e["outcome"] = "pending"
            e["round"] = i + 1
    return events


def unit_history(events: list[dict], fp: str) -> dict:
    evs = sorted((e for e in events if e["fingerprint"] == fp), key=lambda e: e["auction_date"])
    if not evs:
        return {"rounds": 1, "first_price": None, "cut_from_first": 0.0, "events": []}
    first = evs[0]["reserve_price"]
    last = evs[-1]["reserve_price"]
    return {
        "rounds": len(evs),
        "first_price": first,
        "cut_from_first": round(1 - last / first, 4) if first else 0.0,
        "events": [{"date": e["auction_date"], "price": e["reserve_price"], "outcome": e.get("outcome")} for e in evs],
    }


def building_stats(events: list[dict]) -> dict[str, dict]:
    by_b = defaultdict(list)
    for e in events:
        if e["building_key"]:
            by_b[e["building_key"]].append(e)
    today = date.today()
    out = {}
    for bk, evs in by_b.items():
        psfs = [e["reserve_price"] / e["built_up"] for e in evs if e["built_up"]]
        sold = [e for e in evs if e.get("outcome") == "likely_sold"]
        unsold = [e for e in evs if e.get("outcome") == "unsold"]
        recent = [e for e in evs if date.fromisoformat(e["auction_date"]) >= today - timedelta(days=365)]
        out[bk] = {
            "events": len(evs),
            "units": len({e["fingerprint"] for e in evs}),
            "last_12m": len(recent),
            "median_reserve_psf": round(statistics.median(psfs), 1) if psfs else None,
            "sold_psf": round(statistics.median(e["reserve_price"] / e["built_up"] for e in sold if e["built_up"]), 1)
            if any(e["built_up"] for e in sold) else None,
            "sell_through": round(len(sold) / (len(sold) + len(unsold)), 2) if (sold or unsold) else None,
        }
    return out


def load(conn):
    events = infer_outcomes(_events(conn))
    return events, building_stats(events)
