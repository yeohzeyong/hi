from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from auction_tracker import bpl, cleaning, db, finance, history, pipeline, portals, scoring, telegram, transit
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
    assert e["verdict"]["action"] == "BID"

    # second day: nothing new, listing marked as still seen without refetch
    stats2 = pipeline.scrape(conn, f, cfg)
    assert stats2["new"] == 0 and stats2["seen"] == 2

    from auction_tracker import report
    out = report.generate(results, {}, cfg, tmp_path / "docs")
    html = out.read_text()
    assert "Residensi Danau Kota Suites" in html and "</script>" in html


# ------------------------------------------------- multi-source + verdict ----
def test_marketing_slug_and_source():
    u = ("https://www.lelongtips.com.my/property/UnV3WkNaN3dKMkNhL0l4S2hKSWI0QT09/Lelong-Auction-Freehold-Setapak-"
         "Green-Condominium-Strategic-Location-5-min-to-Setapak-Central-Mall-7-min-to-Wangsa-Maju-LRT-Station-in-"
         "Setapak-Kuala-Lumpur-for-RM540000")
    s = bpl.parse_slug(u)
    assert (s["building"], s["property_type"], s["area"], s["reserve_price"]) == ("Setapak Green", "Condominium", "Setapak", 540000)
    assert bpl.source_name(u) == "lelongtips"
    assert bpl.extract_listing_links(f'<a href="{u}">x</a>', "https://www.lelongtips.com.my/search/") == [u]


def test_marketing_slug_does_not_become_building():
    html = "<main><h1>x</h1>Reserve Price RM 333,000<br>Address: Prima Setapak Condominium, Jalan Prima Setapak, 53300</main>"
    u = ("https://central.auctionpro.my/auction/SjlvR0d6MWJlSkVKZlBJL3FZSStMZz09/Lelong-Auction-Nestled-in-a-prime-and-"
         "highly-sought-after-location-Condominium-in-Setapak-Kuala-Lumpur-for-RM333000")
    assert bpl.parse_detail(html, u).building == "Prima Setapak Condominium"


def test_merge_cross_listed():
    base = dict(building_key="danau kota", area_label="Setapak", built_up=1184.0, reserve_price=370000.0,
                auction_date="2026-12-01", dual_key=False, occupied=False, flags=[], address="", building="x",
                unit="", tenure="")
    rows = [{**base, "listing_id": "a", "url": "https://lelongtips/a", "source": "lelongtips"},
            {**base, "listing_id": "b", "url": "https://bpl/b", "source": "bplelonglist", "address": "B-15-07",
             "flags": ["Non-LACA"]}]
    out = pipeline.merge_cross_listed(rows)
    assert len(out) == 1 and out[0]["listing_id"] == "b"
    assert out[0]["also_listed"] == ["https://lelongtips/a"] and out[0]["flags"] == ["Non-LACA"]


def test_verdicts(cfg):
    t = cfg["targets"]
    assert scoring.make_verdict(370000, 386000, 0.29, False, None, t)["action"] == "BID"
    w = scoring.make_verdict(400000, 365000, 0.15, False, None, t)
    assert w["action"] == "WAIT" and w["next_round_price"] == 360000
    assert scoring.make_verdict(500000, 386000, 0.0, False, None, t)["action"] == "PASS"
    assert scoring.make_verdict(370000, 386000, 0.29, True, None, t)["action"] == "VERIFY"
    hot = scoring.make_verdict(370000, 386000, 0.29, False, {"premium_over_reserve": 0.12}, t)
    assert "outbid" in hot["text"]


def test_auction_results_feed_building_stats(tmp_path):
    f = tmp_path / "r.csv"
    f.write_text("auction_date,building,area,built_up,reserve_price,sold_price,source,note\n"
                 "2026-03-01,Residensi Danau Kota Suites,Setapak,1184,400000,452000,fb,\n"
                 "2026-05-01,Danau Kota Suites,Setapak,1184,380000,410000,fb,\n")
    conn = db.connect(tmp_path / "t.db")
    _, b = history.load(conn, f)
    st = b[db.building_key("Residensi Danau Kota Suites")]
    assert st["reported_results"] == 2 and st["actual_sold_psf"] == pytest.approx(363.1, 0.1)
    assert st["premium_over_reserve"] == pytest.approx(0.104, abs=0.001)


def test_occupied_adds_eviction_buffer(cfg):
    lst = {"built_up": 1184, "reserve_price": 370000, "auction_date": None, "flags": [], "dual_key": False}
    plain = scoring.evaluate(lst, None, None, None, {"rounds": 1}, None, {}, cfg)
    occ = scoring.evaluate({**lst, "occupied": True}, None, None, None, {"rounds": 1}, None, {}, cfg)
    assert occ["finance"]["cash_needed"] - plain["finance"]["cash_needed"] == cfg["finance"]["occupied_buffer"]


# ----------------------------------------------------- telegram + fixes ----
TG_PAGE = """
<div class="tgme_widget_message_wrap"><div class="tgme_widget_message" data-post="chrispangauction/101">
 <div class="tgme_widget_message_text">Setapak condo 1,184sf<br>Reserve RM370,000<br>
 <a href="https://www.bplelonglist.com/auction/ZXZMN0pCTVNiRXpQVUFGT25OazlOQT09/Lelong-Auction-Condominium-in-Setapak-Kuala-Lumpur-for-RM370000">details</a></div>
 <a class="tgme_widget_message_date" href="https://t.me/chrispangauction/101"><time datetime="2026-10-01T09:00:00+00:00"></time></a>
</div></div>
<div class="tgme_widget_message_wrap"><div class="tgme_widget_message" data-post="chrispangauction/102">
 <div class="tgme_widget_message_text">SOLD! Residensi Danau Kota, reserve RM400,000, sold at RM452,000. 9 bidders</div>
 <a class="tgme_widget_message_date"><time datetime="2026-10-02T09:00:00+00:00"></time></a>
</div></div>"""


def test_telegram_channel_name():
    assert telegram.channel_name("t.me/MyPropertyInvest/3") == "MyPropertyInvest"
    assert telegram.channel_name("https://t.me/s/chrispangauction") == "chrispangauction"


def test_telegram_collect(tmp_path, monkeypatch):
    monkeypatch.setattr(telegram, "INBOX_FILE", tmp_path / "inbox.csv")

    class F:
        def get(self, url):
            return TG_PAGE if "before" not in url else "<html></html>"
    conn = db.connect(tmp_path / "t.db")
    res = telegram.collect(conn, F(), ["t.me/chrispangauction"], pages=2)
    assert res["stats"]["new_posts"] == 2 and res["stats"]["results"] == 1
    assert res["listing_urls"][0].endswith("for-RM370000")
    inbox = (tmp_path / "inbox.csv").read_text()
    assert "452,000" in inbox and "t.me/chrispangauction/102" in inbox
    again = telegram.collect(conn, F(), ["chrispangauction"], pages=1)
    assert again["stats"]["new_posts"] == 0          # no duplicates on re-run


def test_link_extraction_prefers_full_slug():
    html = ('<a href="/property/Q1Q4TjBBd01PWVFE/Lelong-Auction-Condominium-in-Setapak-Kuala-Lumpur">a</a>'
            '<a href="/property/Q1Q4TjBBd01PWVFE/Lelong-Auction-Condominium-in-Setapak-Kuala-Lumpur-for-RM370000">b</a>')
    assert bpl.extract_listing_links(html, "https://www.lelongtips.com.my/") == [
        "https://www.lelongtips.com.my/property/Q1Q4TjBBd01PWVFE/Lelong-Auction-Condominium-in-Setapak-Kuala-Lumpur-for-RM370000"]


def test_area_label_ignores_marketing_title(tmp_path, cfg):
    conn = db.connect(tmp_path / "t.db")
    url = ("https://www.bplelonglist.com/auction/dVBDYmxLY3VobCtGTW9Z/Lelong-Auction-Hotel-Suite-Nearby-"
           "Bukit-Bintang-in-Brickfields-Kuala-Lumpur-for-RM500000")
    lst = bpl.parse_detail("<main><h1>Suite near Bukit Bintang</h1>Reserve Price RM 500,000</main>", url)
    assert pipeline.save_parsed(conn, lst, cfg) is None
