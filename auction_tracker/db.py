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
    first_seen TEXT, last_seen TEXT, reserve_price REAL, auction_date TEXT, source TEXT, bedrooms INTEGER
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
    if "bedrooms" not in cols:
        conn.execute("ALTER TABLE listings ADD COLUMN bedrooms INTEGER")
    return conn


LISTING_COLS = ["listing_id", "url", "fingerprint", "building_key", "title", "property_type", "area_label",
                "area", "state", "building", "address", "unit", "built_up", "tenure", "title_type", "bumi",
                "dual_key", "occupied", "auctioneer", "bank", "flags", "raw_text", "first_seen", "last_seen",
                "reserve_price", "auction_date", "source", "bedrooms"]


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
           "first_seen": first, "last_seen": last, "source": lst.get("source", ""),
           "bedrooms": lst.get("bedrooms")}
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


# Market comps live in small JSON files (data/comps/<building>.json), not in
# the SQLite file. The cloud run owns tracker.db; your PC owns the comps
# (portals block the cloud). Separate text files mean the two never clash
# when syncing through GitHub.
COMPS_DIR = DATA_DIR / "comps"
COMPS_SCHEMA = 2      # 2 = cheapest-first fetch + bedrooms/type/build year; older files are refetched once


def _comps_file(key: str) -> Path:
    return COMPS_DIR / (re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-") + ".json")


def _has_comps(data: dict) -> bool:
    return any(data.get(k) for k in ("sale", "rent", "area_sale", "area_rent"))


def load_comps(conn, key: str) -> tuple[dict | None, str | None]:
    """(data, fetched_at) from the comps file, else the legacy DB table."""
    f = _comps_file(key)
    if f.exists():
        try:
            blob = json.loads(f.read_text(encoding="utf-8"))
            return blob.get("data"), blob.get("fetched_at")
        except (OSError, json.JSONDecodeError):
            pass
    row = conn.execute("SELECT fetched_at, data FROM comps WHERE query_key=?", (key,)).fetchone()
    return (json.loads(row["data"]), row["fetched_at"]) if row else (None, None)


def get_comps(conn, key: str, max_age_days: int):
    f = _comps_file(key)
    try:
        if f.exists() and json.loads(f.read_text(encoding="utf-8")).get("schema", 1) < COMPS_SCHEMA:
            return None                 # fetched by an older version - refresh (still used until then)
    except (OSError, json.JSONDecodeError):
        return None
    data, fetched = load_comps(conn, key)
    if not data or not fetched or not _has_comps(data):
        return None                     # missing or empty (blocked?) - retry next run
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(fetched)).days
    return data if age <= max_age_days else None


def put_comps(conn, key: str, data: dict):
    if not _has_comps(data):
        return                          # never overwrite good prices with a blocked, empty result
    COMPS_DIR.mkdir(parents=True, exist_ok=True)
    f = _comps_file(key)
    history = []
    if f.exists():
        try:
            history = json.loads(f.read_text(encoding="utf-8")).get("history", [])
        except (OSError, json.JSONDecodeError):
            history = []
    snap = {"date": today()}
    for kind in ("sale", "rent"):
        psfs = sorted(c["price"] / c["built_up"] for c in data.get(kind, []) if c.get("price") and c.get("built_up"))
        if psfs:
            snap[f"{kind}_psf"] = round(psfs[len(psfs) // 2], 2)
            snap[f"{kind}_n"] = len(psfs)
    history = [h for h in history if h.get("date") != snap["date"]] + [snap]
    blob = {"key": key, "schema": COMPS_SCHEMA, "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "data": data, "history": history[-60:]}
    f.write_text(json.dumps(blob, ensure_ascii=False, indent=1), encoding="utf-8")


def comps_history(key: str) -> list[dict]:
    f = _comps_file(key)
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("history", []) if f.exists() else []
    except (OSError, json.JSONDecodeError):
        return []


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
