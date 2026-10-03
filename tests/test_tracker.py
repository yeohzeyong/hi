from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from auction_tracker import bpl, cleaning, db, finance, history, pipeline, portals, scoring, transit
from auction_tracker.config import load_config

FIX = Path(__file__).parent / "fixtures"
DETAIL_URL = ("https://www.bplelonglist.com/auction/ZXZMN0pCTVNiRXpQVUFGT25OazlOQT09/"
              "Lelong-Auction-Condominium-in-Setapak-Kuala-Lumpur-for-RM370000")


@pytest.fixture
def cfg():
    return load_config()


# ---------------------------------------------------------------- bpl ----
def test_search_links_deduped_and_absolute():
    links = bpl.extract_listing_links((FIX / "bpl_search.html").read_text())
    assert len(links) == 2
    assert all(u.startswith("https://www.bplelonglist.com/auction/") for u in links)


def test_parse_slug():
    s = bpl.parse_slug("https://www.bplelonglist.com/auction/X/Lelong-Auction-Aliran-Damai-Apartment-in-Cheras-Kuala-Lumpur-for-RM252000")
    assert s == {"property_type": "Apartment", "building": "Aliran Damai", "area": "Cheras",
                 "state": "Kuala Lumpur", "reserve_price": 252000.0}
    s = bpl.parse_slug("https://www.bplelonglist.com/auction/X/Lelong-Auction-Duplex-Service-Apartment-in-Mont-Kiara-Kuala-Lumpur-for-RM710000")
    assert s["property_type"] == "Duplex Service Apartment" and s["area"] == "Mont Kiara"


def test_parse_detail():
    lst = bpl.parse_detail((FIX / "bpl_detail.html").read_text(), DETAIL_URL)
    assert lst.reserve_price == 370000
    assert lst.built_up == 1184
    assert lst.auction_date == "2026-08-05"
    assert lst.area == "Setapak" and lst.state == "Kuala Lumpur"
    assert lst.building == "Residensi Danau Kota Suites"
    assert lst.unit == "B-15-07"
    assert lst.dual_key and not lst.bumi
    assert lst.tenure.startswith("Leasehold")
    assert lst.title_type == "Strata title"
    assert any("arrears" in f for f in lst.flags)


@pytest.mark.parametrize("raw,iso", [
    ("Wed, Aug 5, 2026", "2026-08-05"),
    ("Thursday, 18 September, 2025", "2025-09-18"),
    ("05/08/2026 (Wednesday) 10:30am", "2026-08-05"),
    ("27th January 2026", "2026-01-27"),
])
def test_parse_date(raw, iso):
    assert bpl.parse_date(raw) == iso


def test_built_up_sqm_conversion():
    assert bpl.parse_built_up("Built-up : 100 sq.m") == pytest.approx(1076.4, 0.1)


# ------------------------------------------------------------- portals ----
def test_pg_next_data_parser_and_mrt():
    comps = portals.listings_from_html((FIX / "pg_sale.html").read_text(), "https://www.propertyguru.com.my/")
    assert len(comps) == 9                              # id 8 duplicates id 1 (same price + size)
    c = comps[0]
    assert c["price"] == 560000 and c["built_up"] == 1184 and c["verified"]
    assert c["mrt"] == {"walk_m": 480, "walk_min": 6, "name": "KG17 Setapak MRT Station"}


def test_building_match():
    assert portals.matches_building({"title": "Danau Kota Suites Setapak"}, "Residensi Danau Kota Suites")
    assert not portals.matches_building({"title": "Some Other Condo Cheras"}, "Residensi Danau Kota Suites")


def test_generic_json_fallback():
    data = {"results": [{"listingId": 5, "askingPrice": "RM 1.2k", "builtUp": "1,050 sq ft", "title": "X"}]}
    out = portals.listings_from_json(data, "https://x.my/")
    assert out[0]["price"] == 1200 and out[0]["built_up"] == 1050


# ------------------------------------------------------------ cleaning ----
def test_cleaning_removes_fakes(cfg):
    raw = portals.listings_from_html((FIX / "pg_sale.html").read_text(), "https://www.propertyguru.com.my/")
    raw = [c for c in raw if portals.matches_building(c, "Residensi Danau Kota Suites")]
    kept, removed = cleaning.clean_comps(raw, "sale", 1184, cfg["cleaning"])
    reasons = " ".join(r["reason"] for r in removed)
    assert "keyword" in reasons and "lowball" in reasons and "different unit size" in reasons
    assert {c["price"] for c in kept} == {560000, 580000, 540000, 600000, 570000}
    s = cleaning.summarize(kept, 1184, "sale", cfg["cleaning"])
    assert s["confident"] and 470000 < s["estimate"] < 560000


def test_cleaning_drops_room_rentals(cfg):
    raw = portals.listings_from_html((FIX / "pg_rent.html").read_text(), "https://www.propertyguru.com.my/")
    kept, removed = cleaning.clean_comps(raw, "rent", 1184, cfg["cleaning"])
    assert all(c["price"] > 2000 for c in kept)
    assert any("room" in r["reason"] for r in removed)


# ------------------------------------------------------------- finance ----
def test_installment_known_value():
    # RM333,000 @ 4.3% over 35 years ~ RM1,535/month
    assert finance.monthly_installment(333000, 0.043, 35) == pytest.approx(1535, abs=5)


def test_stamp_duty_scale():
    assert finance.stamp_duty_transfer(100_000) == 1000
    assert finance.stamp_duty_transfer(500_000) == 9000
    assert finance.stamp_duty_transfer(1_000_000) == 24000


def test_max_bid_meets_targets(cfg):
    fin, tgt = cfg["finance"], cfg["targets"]
    mb = finance.max_bid(1184, 2400, 560000, fin, tgt)
    a = finance.analyse(mb["max_bid"], 1184, 2400, fin, 560000)
    assert a["rent_cover"] >= tgt["min_rent_cover"] - 0.01
    assert a["discount"] >= tgt["min_discount"]


# ------------------------------------------------------------- transit ----
def test_nearest_station():
    st = [{"name": "A", "lat": 3.2, "lon": 101.7, "type": "MRT"},
          {"name": "K", "lat": 3.2001, "lon": 101.7001, "type": "KTM"}]
    best = transit.nearest_station(3.204, 101.7, st, detour=1.0)
    assert best["name"] == "A" and 430 < best["walk_m"] < 460


# ------------------------------------------------------------- history ----
def test_history_rounds_and_outcomes(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    base = dict(url="u", title="t", property_type="Condominium", area="Setapak", state="Kuala Lumpur",
                building="Residensi Danau Kota Suites", address="", unit="B-15-07", built_up=1184.0,
                tenure="", title_type="", bumi=False, dual_key=False, occupied=False, auctioneer="",
                bank="", flags=[], raw_text="")
    d1 = (date.today() - timedelta(days=200)).isoformat()
    d2 = (date.today() + timedelta(days=20)).isoformat()
    db.upsert_listing(conn, {**base, "listing_id": "old", "reserve_price": 411000.0, "auction_date": d1}, "Setapak")
    db.upsert_listing(conn, {**base, "listing_id": "new", "reserve_price": 370000.0, "auction_date": d2}, "Setapak")
    events, bstats = history.load(conn)
    fp = db.fingerprint("Residensi Danau Kota Suites", "B-15-07", 1184, "Setapak")
    uh = history.unit_history(events, fp)
    assert uh["rounds"] == 2 and uh["events"][0]["outcome"] == "unsold"
    assert uh["cut_from_first"] == pytest.approx(0.0998, abs=1e-3)
    assert bstats[db.building_key("Residensi Danau Kota Suites")]["units"] == 1


# ----------------------------------------------------------- end to end ----
class FakeFetcher:
    def __init__(self):
        self.pages = {
            "search": (FIX / "bpl_search.html").read_text(),
            "detail": (FIX / "bpl_detail.html").read_text(),
            "sale": (FIX / "pg_sale.html").read_text(),
            "rent": (FIX / "pg_rent.html").read_text(),
        }

    def get(self, url):
        if "/search/" in url:
            return self.pages["search"] if "page=1&" in url and "Setapak" in url else "<html></html>"
        if "/auction/" in url:
            if "Mont-Kiara" in url:
                return "<html><main><h1>x</h1>Reserve Price RM 300,000 Built-up 850 sq.ft</main></html>"
            return self.pages["detail"]
        if "property-for-sale" in url:
            return self.pages["sale"]
        if "property-for-rent" in url:
            return self.pages["rent"]
        return "<html></html>"


def test_pipeline_end_to_end(tmp_path, cfg, monkeypatch):
    monkeypatch.setattr(pipeline, "OVERRIDES_FILE", tmp_path / "none.yaml")
    monkeypatch.setattr(pipeline, "MANUAL_COMPS_FILE", tmp_path / "none.csv")
    monkeypatch.setattr(transit, "GEOCODE_FILE", tmp_path / "geo.json")
    # pretend the auction is in the future
    detail = (FIX / "bpl_detail.html").read_text().replace("Aug 5, 2026", (date.today() + timedelta(days=30)).strftime("%b %d, %Y"))
    f = FakeFetcher()
    f.pages["detail"] = detail
    conn = db.connect(tmp_path / "t.db")
    stats = pipeline.scrape(conn, f, cfg)
    assert stats["new"] == 2
    pipeline.refresh_comps(conn, f, cfg)
    results = pipeline.evaluate_all(conn, cfg, geocode=False)
    assert len(results) == 1                          # Mont Kiara one is < 1000 sqft
    e = results[0]
    assert e["status"] == "ok"
    assert e["station"]["source"] == "portal" and e["station"]["walk_m"] == 480
    assert e["finance"]["rent_cover"] > 1.0
    assert e["finance"]["discount"] > 0.2
    assert e["grade"] == "A", (e["score"], e["parts"], e["cons"], e["notes"])

    # second day: nothing new, listing marked as still seen without refetch
    stats2 = pipeline.scrape(conn, f, cfg)
    assert stats2["new"] == 0 and stats2["seen"] == 2

    from auction_tracker import report
    out = report.generate(results, {}, cfg, tmp_path / "docs")
    html = out.read_text()
    assert "Residensi Danau Kota Suites" in html and "</script>" in html
