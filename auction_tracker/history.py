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

import csv
import statistics
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from .config import DATA_DIR

RESULTS_FILE = DATA_DIR / "auction_results.csv"


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


def load_results(path: Path | None = None) -> list[dict]:
    """Real outcomes you collect (Facebook groups, auctioneers, lelongtips
    'sold' posts): auction_date,building,area,built_up,reserve_price,sold_price,source,note"""
    from .db import building_key
    path = path or RESULTS_FILE
    if not path.exists():
        return []
    out = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                sold = float(row["sold_price"]) if row.get("sold_price") else None
                reserve = float(row["reserve_price"]) if row.get("reserve_price") else None
                sqft = float(row["built_up"]) if row.get("built_up") else None
            except ValueError:
                continue
            if not row.get("building") or not (sold or reserve):
                continue
            out.append({"building_key": building_key(row["building"]), "area": row.get("area", ""),
                        "date": row.get("auction_date", ""), "sold": sold, "reserve": reserve, "sqft": sqft})
    return out


def merge_results(bstats: dict, results: list[dict]) -> dict:
    by_b = defaultdict(list)
    for r in results:
        by_b[r["building_key"]].append(r)
    for bk, rs in by_b.items():
        st = bstats.setdefault(bk, {"events": 0, "units": 0, "last_12m": 0, "median_reserve_psf": None,
                                    "sold_psf": None, "sell_through": None})
        sold = [r for r in rs if r["sold"] and r["sqft"]]
        prem = [r["sold"] / r["reserve"] - 1 for r in rs if r["sold"] and r["reserve"]]
        st["reported_results"] = len(rs)
        if sold:
            st["actual_sold_psf"] = round(statistics.median(r["sold"] / r["sqft"] for r in sold), 1)
            st["sold_psf"] = st["actual_sold_psf"]          # real data beats inference
        if prem:
            st["premium_over_reserve"] = round(statistics.median(prem), 3)
    return bstats


def load(conn, results_path: Path | None = None):
    events = infer_outcomes(_events(conn))
    return events, merge_results(building_stats(events), load_results(results_path))
