"""SQLite store. Every daily run appends observations, which over months
becomes your own auction history database (price rounds, relistings,
which buildings keep coming back to auction)."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from .config import DATA_DIR

DB_PATH = DATA_DIR / "tracker.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    listing_id TEXT PRIMARY KEY,
    url TEXT, fingerprint TEXT, building_key TEXT,
    title TEXT, property_type TEXT, area_label TEXT, area TEXT, state TEXT,
    building TEXT, address TEXT, unit TEXT, built_up REAL,
    tenure TEXT, title_type TEXT, bumi INTEGER, dual_key INTEGER, occupied INTEGER,
    auctioneer TEXT, bank TEXT, flags TEXT, raw_text TEXT,
    first_seen TEXT, last_seen TEXT, reserve_price REAL, auction_date TEXT, source TEXT
);
CREATE INDEX IF NOT EXISTS ix_listings_fp ON listings(fingerprint);
CREATE INDEX IF NOT EXISTS ix_listings_bk ON listings(building_key);
CREATE TABLE IF NOT EXISTS observations (
    listing_id TEXT, seen_date TEXT, reserve_price REAL, auction_date TEXT,
    PRIMARY KEY (listing_id, seen_date)
);
CREATE TABLE IF NOT EXISTS comps (
    query_key TEXT PRIMARY KEY, fetched_at TEXT, data TEXT
);
CREATE TABLE IF NOT EXISTS evaluations (
    listing_id TEXT PRIMARY KEY, run_date TEXT, grade TEXT, score REAL, data TEXT
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS notified (
    listing_id TEXT, grade TEXT, reserve_price REAL, notified_at TEXT,
    PRIMARY KEY (listing_id, reserve_price)
);
"""

NAME_NOISE = r"\b(kondominium|condominium|condo|pangsapuri|servis|service[d]?|apartment|residensi|residence[s]?|suites?|the|at|@)\b"


def building_key(building: str) -> str:
    s = re.sub(NAME_NOISE, " ", (building or "").lower())
    return " ".join(re.findall(r"[a-z0-9]+", s))


def fingerprint(building: str, unit: str, built_up: float | None, area: str) -> str:
    """Identify the *same physical unit* across re-auctions (new listing ids)."""
    bk = building_key(building) or building_key(area)
    if unit:
        return f"{bk}|{unit.upper()}"
    return f"{bk}|{round(built_up or 0)}sqft"


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(listings)")}
    if "source" not in cols:                       # migrate older databases
        conn.execute("ALTER TABLE listings ADD COLUMN source TEXT")
    return conn


LISTING_COLS = ["listing_id", "url", "fingerprint", "building_key", "title", "property_type", "area_label",
                "area", "state", "building", "address", "unit", "built_up", "tenure", "title_type", "bumi",
                "dual_key", "occupied", "auctioneer", "bank", "flags", "raw_text", "first_seen", "last_seen",
                "reserve_price", "auction_date", "source"]


def today() -> str:
    return date.today().isoformat()


def upsert_listing(conn, lst: dict, area_label: str, seen_now: bool = True):
    """seen_now=False (re-parsing stored pages) keeps the sighting history intact."""
    now = today()
    fp = fingerprint(lst["building"], lst["unit"], lst["built_up"], lst["area"])
    row = conn.execute("SELECT first_seen, last_seen FROM listings WHERE listing_id=?", (lst["listing_id"],)).fetchone()
    first = row["first_seen"] if row else now
    last = now if (seen_now or not row) else row["last_seen"]
    row = {**lst, "fingerprint": fp, "building_key": building_key(lst["building"]), "area_label": area_label,
           "flags": json.dumps(lst.get("flags", [])), "bumi": int(lst["bumi"]),
           "dual_key": int(lst["dual_key"]), "occupied": int(lst["occupied"]),
           "first_seen": first, "last_seen": last, "source": lst.get("source", "")}
    conn.execute(f"INSERT OR REPLACE INTO listings ({','.join(LISTING_COLS)}) "
                 f"VALUES ({','.join(':' + c for c in LISTING_COLS)})", row)
    if seen_now:
        observe(conn, lst["listing_id"], lst["reserve_price"], lst["auction_date"])


def observe(conn, listing_id: str, price, auction_date, seen: str | None = None):
    seen = seen or today()
    conn.execute("INSERT OR REPLACE INTO observations VALUES (?,?,?,?)", (listing_id, seen, price, auction_date))
    conn.execute("UPDATE listings SET last_seen=? WHERE listing_id=? AND (last_seen IS NULL OR last_seen<?)",
                 (seen, listing_id, seen))


def get_meta(conn, key: str, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn, key: str, value):
    conn.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, str(value)))


def get_comps(conn, key: str, max_age_days: int):
    row = conn.execute("SELECT fetched_at, data FROM comps WHERE query_key=?", (key,)).fetchone()
    if not row:
        return None
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(row["fetched_at"])).days
    data = json.loads(row["data"])
    if not any(data.get(k) for k in ("sale", "rent", "area_sale", "area_rent")):
        return None                     # an empty result (blocked?) is retried next run
    return data if age <= max_age_days else None


def put_comps(conn, key: str, data: dict):
    conn.execute("INSERT OR REPLACE INTO comps VALUES (?,?,?)",
                 (key, datetime.now(timezone.utc).isoformat(timespec="seconds"), json.dumps(data)))


def listing_rows(conn):
    rows = conn.execute("SELECT * FROM listings").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["flags"] = json.loads(d["flags"] or "[]")
        for b in ("bumi", "dual_key", "occupied"):
            d[b] = bool(d[b])
        out.append(d)
    return out
