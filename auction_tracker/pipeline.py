"""Orchestrates: scrape -> comps -> evaluate -> report -> notify."""

from __future__ import annotations

import csv
import json
import logging
from datetime import date, timedelta

from . import bpl, db, history, portals, scoring, telegram, transit
from .cleaning import clean_comps, summarize
from .config import DATA_DIR, load_yaml

log = logging.getLogger(__name__)

OVERRIDES_FILE = DATA_DIR / "building_overrides.yaml"
MANUAL_COMPS_FILE = DATA_DIR / "manual_comps.csv"


# ---------------------------------------------------------------------------
# 1. Scrape
# ---------------------------------------------------------------------------
def save_parsed(conn, lst: bpl.Listing, cfg: dict, seen_now: bool = True) -> str | None:
    d = lst.to_dict()
    # Use the real location (area from the URL, then the address). Advert
    # titles often name-drop nearby areas ("... near Bukit Bintang") for
    # units that are actually in Pudu or Brickfields.
    areas = cfg["search"]["areas"]
    label = scoring.matched_area(d["area"], areas) or scoring.matched_area(d["address"], areas)
    want_state = cfg["search"].get("state", "")
    if label and want_state and d.get("state") and d["state"].lower() != want_state.lower():
        label = None          # e.g. "Cheras" in Selangor when you want KL
    if not label and not d["area"] and not d["address"]:
        label = scoring.matched_area(f"{d['title']} {d['building']}", areas)
    db.upsert_listing(conn, d, label or "", seen_now=seen_now)
    return label


def reparse_if_parser_changed(conn, cfg: dict):
    if db.get_meta(conn, "parser_version") != str(bpl.PARSER_VERSION):
        log.info("parser updated - re-parsing stored listings")
        reparse(conn, cfg)
        db.set_meta(conn, "parser_version", bpl.PARSER_VERSION)
        conn.commit()


def scrape(conn, fetcher, cfg: dict, backfill: bool = False) -> dict:
    reparse_if_parser_changed(conn, cfg)
    s = cfg["search"]
    known = {r["listing_id"]: r for r in conn.execute("SELECT listing_id, reserve_price, auction_date FROM listings")}
    known_ids = set(known)
    seen: dict[str, str] = {}
    stats = {"new": 0, "updated": 0, "seen": 0, "search_pages": 0}
    keywords = [k for kws in s["areas"].values() for k in kws]
    pages = s["backfill_max_pages"] if backfill else s["max_pages_per_keyword"]
    sources = cfg.get("sources") or {"bplelonglist": bpl.DEFAULT_SEARCH}
    for name, template in sources.items():
        src_stats = {"search_pages": 0}
        # Walk every result page (up to the cap) so still-listed units keep
        # being marked as seen - auction-history inference relies on it.
        for url, html in bpl.crawl(fetcher, s["state"], keywords, pages, known_ids,
                                   stop_after_known_pages=0, seen_sink=seen, stats=src_stats,
                                   template=template):
            save_parsed(conn, bpl.parse_detail(html, url), cfg)
            stats["new"] += 1
            conn.commit()
        stats["search_pages"] += src_stats["search_pages"]
        stats[f"pages_{name}"] = src_stats["search_pages"]
        if not src_stats["search_pages"]:
            log.error("source %s returned no search pages (blocked or changed?)", name)
    # Listings already known: still listed today. Re-fetch only when the
    # reserve price in the URL slug changed (a new round / correction).
    for lid, url in seen.items():
        if lid not in known:
            continue
        stats["seen"] += 1
        slug_price = bpl.parse_slug(url).get("reserve_price")
        old = known[lid]
        if slug_price and old["reserve_price"] and abs(slug_price - old["reserve_price"]) > 1:
            try:
                save_parsed(conn, bpl.parse_detail(bpl.fetch_detail(fetcher, url), url), cfg)
                stats["updated"] += 1
            except Exception as exc:
                log.warning("refresh failed %s: %s", url, exc)
        else:
            db.observe(conn, lid, old["reserve_price"], old["auction_date"])
    conn.commit()
    log.info("scrape: %s", stats)
    return stats


def scrape_telegram(conn, fetcher, cfg: dict, backfill: bool = False) -> dict:
    """Analyse auction links that agents post in public Telegram channels."""
    channels = cfg.get("telegram_channels") or []
    if not channels:
        return {}
    res = telegram.collect(conn, fetcher, channels, pages=10 if backfill else 2)
    known = {r["listing_id"] for r in conn.execute("SELECT listing_id FROM listings")}
    added = 0
    for url in res["listing_urls"]:
        if bpl.listing_id_from_url(url) in known:
            continue
        try:
            save_parsed(conn, bpl.parse_detail(bpl.fetch_detail(fetcher, url), url), cfg)
            added += 1
        except Exception as exc:
            log.warning("telegram listing failed %s: %s", url, exc)
    for lst in res.get("listings", []):
        save_parsed(conn, lst, cfg)       # re-saving refreshes last_seen / price
        added += lst.listing_id not in known
    conn.commit()
    res["stats"]["listings_added"] = added
    return res["stats"]


def reparse(conn, cfg: dict):
    """Re-run the parser over stored page text (after improving the parser).
    Telegram listings are skipped - their posts are re-parsed on every run."""
    for r in conn.execute("SELECT listing_id, url, raw_text FROM listings "
                          "WHERE COALESCE(source,'') NOT LIKE 'telegram%'").fetchall():
        html = "<main>" + "".join(f"<p>{line}</p>" for line in (r["raw_text"] or "").split("\n")) + "</main>"
        lst = bpl.parse_detail(html, r["url"])
        save_parsed(conn, lst, cfg, seen_now=False)
    conn.commit()


# ---------------------------------------------------------------------------
# 2. Market comps
# ---------------------------------------------------------------------------
def candidate_listings(conn, cfg: dict, active_only: bool = True) -> list[dict]:
    s = cfg["search"]
    today = date.today().isoformat()
    cutoff = (date.today() - timedelta(days=7)).isoformat()
    out = []
    for r in db.listing_rows(conn):
        if not r["area_label"]:
            continue
        if not scoring.is_residential_type(r["property_type"] or "", r["title"] or "", s["property_types"]):
            continue
        if r["built_up"] and r["built_up"] < s["min_built_up_sqft"]:
            continue
        if active_only:
            # Upcoming auction date = active. Without a date, require a recent sighting.
            if r["auction_date"] and r["auction_date"] < today:
                continue
            if not r["auction_date"] and r["last_seen"] < cutoff:
                continue
        out.append(r)
    return merge_cross_listed(out)


def merge_cross_listed(rows: list[dict]) -> list[dict]:
    """The same auction often appears on several sites. Keep the most complete
    record and remember the other URLs."""
    def completeness(r):
        return (sum(bool(r.get(k)) for k in ("built_up", "auction_date", "address", "building", "unit", "tenure")),
                r.get("source") == "bplelonglist")
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        key = (r["building_key"] or r["area_label"], round((r["built_up"] or 0) / 10),
               round(r["reserve_price"] or 0, -2), r["auction_date"] or r["listing_id"])
        groups.setdefault(key, []).append(r)
    out = []
    for grp in groups.values():
        grp.sort(key=completeness, reverse=True)
        best = dict(grp[0])
        best["also_listed"] = [g["url"] for g in grp[1:]]
        best["dual_key"] = any(g["dual_key"] for g in grp)
        best["occupied"] = any(g["occupied"] for g in grp)
        best["flags"] = sorted({f for g in grp for f in g["flags"]})
        out.append(best)
    return out


def comps_key(r: dict) -> tuple[str, str, str | None]:
    """(cache key, search query, building name to match)"""
    if r["building"] and db.building_key(r["building"]):
        return f"b:{db.building_key(r['building'])}", r["building"], r["building"]
    return f"a:{r['area_label'].lower()}", f"{r['area_label']} condominium", None


def refresh_comps(conn, fetcher, cfg: dict, force: bool = False, limit: int | None = None) -> int:
    done = 0
    pcfg = {k: v for k, v in cfg["portals"].items() if isinstance(v, dict)}
    max_age = cfg["portals"].get("cache_days", 21)
    memo: dict[tuple, dict] = {}

    def fetch(query, building, pages):
        key = (query, building)
        if key not in memo:          # area-level searches repeat across buildings
            memo[key] = portals.fetch_comps(fetcher, pcfg, query, building, pages)
        return memo[key]

    for r in candidate_listings(conn, cfg):
        key, query, building = comps_key(r)
        if not force and db.get_comps(conn, key, max_age) is not None:
            continue
        pages = cfg["portals"].get("pages", 1)
        data = dict(fetch(query, building, pages))
        if building and (len(data["sale"]) < 2 or len(data["rent"]) < 2):
            log.info("few building comps for %r; also fetching area-level comps", building)
            area = fetch(f"{r['area_label']} condominium", None, pages)
            data["area_sale"], data["area_rent"] = area["sale"], area["rent"]
        db.put_comps(conn, key, data)
        conn.commit()
        done += 1
        if limit and done >= limit:
            break
    return done


def manual_comps() -> dict[str, dict[str, list]]:
    out: dict[str, dict[str, list]] = {}
    if not MANUAL_COMPS_FILE.exists():
        return out
    with open(MANUAL_COMPS_FILE, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if not row.get("building") or not row.get("price") or not row.get("built_up"):
                continue
            bk = db.building_key(row["building"])
            kind = row.get("kind", "sale").strip().lower()
            out.setdefault(bk, {"sale": [], "rent": []}).setdefault(kind, []).append({
                "id": f"manual-{len(out[bk][kind])}", "title": row.get("note", "") or "manual",
                "description": "", "price": float(row["price"]), "built_up": float(row["built_up"]),
                "url": row.get("source", ""), "portal": "manual", "kind": kind, "dual_key": False,
            })
    return out


def _summaries(conn, r: dict, cfg: dict, manual: dict) -> tuple[dict | None, dict | None, dict]:
    key, _, _ = comps_key(r)
    row = conn.execute("SELECT data FROM comps WHERE query_key=?", (key,)).fetchone()
    data = json.loads(row["data"]) if row else {"sale": [], "rent": []}
    extra = manual.get(db.building_key(r["building"] or ""), {})
    debug = {}
    out = []
    for kind in ("sale", "rent"):
        raw = data.get(kind, []) + extra.get(kind, [])
        kept, removed = clean_comps(raw, kind, r["built_up"], cfg["cleaning"])
        scope = "building"
        if len(kept) < 2 and data.get(f"area_{kind}"):
            kept, removed2 = clean_comps(data[f"area_{kind}"], kind, r["built_up"], cfg["cleaning"])
            removed += removed2
            scope = "area"
        summ = summarize(kept, r["built_up"], kind, cfg["cleaning"])
        if summ:
            summ["scope"] = scope
            if scope == "area":
                summ["confident"] = False
        out.append(summ)
        debug[kind] = {"kept": kept[:30], "removed": removed[:30], "raw_count": len(raw)}
    return out[0], out[1], debug


# ---------------------------------------------------------------------------
# 3. Evaluate
# ---------------------------------------------------------------------------
def _override_for(overrides: dict, r: dict) -> dict:
    o = {}
    by_key = {db.building_key(k): v for k, v in (overrides.get("buildings") or {}).items()}
    o.update(by_key.get(db.building_key(r["building"] or ""), {}) or {})
    o.update((overrides.get("listings") or {}).get(r["listing_id"], {}) or {})
    return o


def evaluate_all(conn, cfg: dict, geocode: bool = True) -> list[dict]:
    overrides = load_yaml(OVERRIDES_FILE, {"buildings": {}, "listings": {}})
    manual = manual_comps()
    events, bstats = history.load(conn)
    stations = transit.load_stations(cfg["transit"]["bbox"]) if geocode else []
    geo = transit.Geocoder()
    results = []
    run_date = db.today()
    for r in candidate_listings(conn, cfg):
        ov = _override_for(overrides, r)
        if ov.get("dual_key") is not None:
            r["dual_key"] = bool(ov["dual_key"])
        sale, rent, debug = _summaries(conn, r, cfg, manual)
        station = None
        if ov.get("lat") and ov.get("lon"):
            loc = (ov["lat"], ov["lon"])
        elif geocode:
            loc = geo.locate(r["building"], r["address"], r["area"] or r["area_label"], r["state"] or "Kuala Lumpur")
        else:
            loc = None
        if loc and stations:
            station = transit.nearest_station(loc[0], loc[1], stations, cfg["transit"]["walk_detour_factor"])
        if station is None:
            station = station_from_comps(debug)
        uh = history.unit_history(events, r["fingerprint"])
        ev = scoring.evaluate(r, sale, rent, station, uh, bstats.get(r["building_key"]), ov, cfg)
        ev["listing"] = {k: r[k] for k in ("listing_id", "url", "title", "property_type", "area_label", "area",
                                           "building", "address", "unit", "built_up", "reserve_price",
                                           "auction_date", "tenure", "title_type", "bumi", "dual_key",
                                           "occupied", "auctioneer", "bank", "first_seen", "last_seen",
                                           "source")}
        ev["listing"]["also_listed"] = r.get("also_listed", [])
        ev["location"] = list(loc) if loc else None
        ev["comps_debug"] = debug
        ev["links"] = research_links(r)
        conn.execute("INSERT OR REPLACE INTO evaluations VALUES (?,?,?,?,?)",
                     (r["listing_id"], run_date, ev["grade"], ev["score"], json.dumps(ev, default=str)))
        results.append(ev)
    geo.save()
    conn.commit()
    results.sort(key=lambda e: (scoring.GRADE_ORDER[e["grade"]], e["score"]), reverse=True)
    return results


def station_from_comps(debug: dict) -> dict | None:
    """Fallback: portals print '7 min (570 m) from X MRT Station' on listings
    in the same building - take the median of what agents report."""
    hits = [c["mrt"] for kind in ("rent", "sale") for c in debug.get(kind, {}).get("kept", [])
            if c.get("mrt") and c.get("portal") != "manual"]
    if not hits:
        return None
    hits.sort(key=lambda h: h["walk_m"])
    mid = hits[len(hits) // 2]
    return {"name": mid["name"], "type": transit.classify_station({"name": mid["name"]}),
            "walk_m": mid["walk_m"], "walk_min": mid["walk_min"], "source": "portal"}


def research_links(r: dict) -> dict:
    from urllib.parse import quote_plus
    q = quote_plus(r["building"] or f"{r['area_label']} condominium")
    return {
        "listing": r["url"],
        "propertyguru_sale": f"https://www.propertyguru.com.my/property-for-sale?freetext={q}",
        "propertyguru_rent": f"https://www.propertyguru.com.my/property-for-rent?freetext={q}",
        "iproperty_sale": f"https://www.iproperty.com.my/property-for-sale?freetext={q}",
        "iproperty_rent": f"https://www.iproperty.com.my/property-for-rent?freetext={q}",
        "brickz_transactions": f"https://www.brickz.my/transactions/residential/?q={q}",
        "google_maps": f"https://www.google.com/maps/search/?api=1&query={quote_plus((r['building'] or '') + ' ' + (r['area'] or r['area_label']) + ' Kuala Lumpur')}",
    }
