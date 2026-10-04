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
    assert "keyword" in reasons and "lowball" in reasons and "size +103%" in reasons
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


# ------------------------------------------- real-format regression tests ----
BPL_REAL = """Home
Auction
Property Details
Auction Property Details
Service Apartment
Residensi Agile Delima, Kuala Lumpur
Reserve Price
RM 633,000.00
Auction Details
Property Address:
Unit No.
, Residensi Agile Delima, Jalan Delima, Bukit Bintang, 55100, Kuala Lumpur
Auction Date:
Thursday, 8 Oct, 2026
Reserve Price:
RM 633,000.00
Deposit:
5%
Built Up:
703 sq.ft
Tenure:
Freehold
Related Auctions
RM 562,000.00
Service Apartment
625 sq.ft"""


def test_bpl_real_page_layout():
    html = "<h1>bplelonglist.com</h1><main>" + "".join(f"<p>{l}</p>" for l in BPL_REAL.split("\n")) + "</main>"
    url = ("https://www.bplelonglist.com/auction/ekFUSHBNNE5nNWpMd0FQSTlKMXpNZz09/"
           "Lelong-Auction-Service-Apartment-in-Bukit-Bintang-Kuala-Lumpur-for-RM633000")
    l = bpl.parse_detail(html, url)
    assert l.building == "Residensi Agile Delima"
    assert l.address == "Unit No., Residensi Agile Delima, Jalan Delima, Bukit Bintang, 55100, Kuala Lumpur"
    assert (l.property_type, l.built_up, l.reserve_price, l.auction_date) == ("Service Apartment", 703, 633000, "2026-10-08")
    assert l.tenure == "Freehold" and "Auction-day deposit is 5% (not the usual 10%)" in l.flags


YUKI = """🏠
D'sands Residence @ Old Klang Road
✅
Service Apartment
✅
Size 1313 sqft
✅
Freehold
✅
Non Bumi Lot
📍
No. B1-09-1, Block 1, D'Sands Residence (Residensi Pasir Emas), Jalan Kampung Pasir, Off Jalan Klang Lama, 58200, Kuala Lumpur
💥
Lelong Price
💥
RM 475k
💥
** Market Value : RM 720k
📆
Lelong Date : 22/10/2026"""

CHRIS = """Parc 3 @ Cheras
📍
Unit No. 33-12, Parc 3, No. 5, Jalan Pudu Perdana, 56100, Kuala Lumpur
✅
Service Apartment
✅
Built Up 1453 sq.ft
🔥
Auction Price RM 729k
🔥
Market Value RM 1mil
📅
Auction Date 7/10/26"""

TRINITY = """𝐂𝐎𝐍𝐃𝐎𝐌𝐈𝐍𝐈𝐔𝐌 𝐈𝐍 𝐁𝐔𝐊𝐈𝐓 𝐉𝐀𝐋𝐈𝐋!
Location: Residensi Parkhill, No. 12, Lebuhraya Bukit Jalil, 57000, Kuala Lumpur.
𝐔𝐧𝐢𝐭 𝐍𝐨: 𝐂-𝟑𝟐-𝟎𝟑, 𝐓𝐨𝐰𝐞𝐫 𝐂.
Size: 1,100 sq.ft.
Market Price: RM560,000
Auction Price: RM416,000
Auction Date: 8th October 2026
𝐔𝐧𝐢𝐭 𝐍𝐨: 𝐂-𝟑𝟐-𝟑𝐀, 𝐓𝐨𝐰𝐞𝐫 𝐂.
Size: 1,100 sq.ft.
Market Price: RM560,000
Auction Price: RM500,000
Auction Date: 21st October 2026
(Potential Rental: RM2,500 - RM2,800)
Tenure: Leasehold (Till 2114)
Type: Condominium
Status: Occupied"""


def test_telegram_listing_posts():
    y = telegram.parse_post_listings({"channel": "yuki", "post_id": 1, "text": YUKI})[0]
    assert (y.building, y.unit, y.built_up, y.reserve_price, y.auction_date) == (
        "D'Sands Residence (Residensi Pasir Emas)", "B1-09-1", 1313, 475000, "2026-10-22")
    assert y.state == "Kuala Lumpur" and not y.bumi and y.property_type == "Service Apartment"
    assert any("Agent claims market value RM720,000" in f for f in y.flags)

    c = telegram.parse_post_listings({"channel": "chris", "post_id": 2, "text": CHRIS})[0]
    assert (c.area, c.building, c.reserve_price, c.auction_date, c.built_up) == ("Cheras", "Parc 3", 729000, "2026-10-07", 1453)

    t = telegram.parse_post_listings({"channel": "trinity", "post_id": 3, "text": TRINITY})
    assert [(x.unit, x.reserve_price, x.auction_date) for x in t] == [
        ("C-32-03", 416000, "2026-10-08"), ("C-32-3A", 500000, "2026-10-21")]
    assert all(x.occupied and x.tenure.startswith("Leasehold") and x.building == "Residensi Parkhill" for x in t)


def test_state_filter_drops_selangor_cheras(tmp_path, cfg):
    conn = db.connect(tmp_path / "t.db")
    lst = bpl.Listing(listing_id="x", url="u", area="", state="Selangor",
                      address="Unit No. B-11-1, Akasa Cheras, Jalan Akasa, Akasa Cheras Selatan, 43300 Seri Kembangan, Selangor")
    assert pipeline.save_parsed(conn, lst, cfg) is None


def test_reparse_keeps_sighting_history(tmp_path, cfg):
    conn = db.connect(tmp_path / "t.db")
    lst = bpl.parse_detail("<main>" + "".join(f"<p>{l}</p>" for l in BPL_REAL.split("\n")) + "</main>",
                           "https://www.bplelonglist.com/auction/ekFUSHBNNE5nNWpMd0FQSTlKMXpNZz09/x-for-RM633000")
    pipeline.save_parsed(conn, lst, cfg)
    conn.execute("UPDATE listings SET last_seen='2026-01-01'")
    conn.execute("DELETE FROM observations")
    pipeline.reparse(conn, cfg)
    assert conn.execute("SELECT last_seen FROM listings").fetchone()[0] == "2026-01-01"
    assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0


# ----------------------------------------------------- like-for-like comps ----
def _comp(i, price, sqft, title="Residensi X", ptype="Condominium", beds=3, furn=""):
    return {"id": str(i), "price": price, "built_up": sqft, "title": title, "ptype": ptype,
            "bedrooms": beds, "furnishing": furn, "description": "", "url": f"u{i}"}


def test_type_groups():
    assert cleaning.type_group("Duplex Service Apartment") == "duplex/penthouse"
    assert cleaning.type_group("Service Apartment") == "serviced"
    assert cleaning.type_group("Pangsapuri Vista") == "apartment"
    assert cleaning.type_group("Kondominium Kiara") == "condo"


def test_like_for_like_selection(cfg):
    subject = {"built_up": 1100, "property_type": "Condominium", "bedrooms": 3}
    comps = [_comp(1, 550000, 1100), _comp(2, 560000, 1150), _comp(3, 540000, 1050), _comp(4, 570000, 1180),
             _comp(5, 900000, 1500),                                     # size +36%
             _comp(6, 500000, 1100, ptype="Duplex"),                    # other type
             _comp(7, 450000, 1100, beds=2),                            # other bedrooms
             _comp(8, 615000, 1250)]                                    # +14%: inside T1
    kept, removed, crit = cleaning.select_comparables(comps, "sale", subject, cfg["cleaning"])
    assert {c["id"] for c in kept} == {"1", "2", "3", "4", "8"}
    assert crit["tier"] == "T1" and crit["size_band"] == 0.15
    why = {c["id"]: c["reason"] for c in removed}
    assert "size +36%" in why["5"] and "different type" in why["6"] and "2 bedrooms" in why["7"]
    assert "same building" in kept[0]["match"] and "3BR" in kept[0]["match"]


def test_band_widens_only_when_needed(cfg):
    subject = {"built_up": 1000, "property_type": "Condominium"}
    comps = [_comp(1, 500000, 1000, beds=None), _comp(2, 600000, 1200, beds=None),
             _comp(3, 612000, 1220, beds=None), _comp(4, 398000, 800, beds=None)]
    kept, _, crit = cleaning.select_comparables(comps, "sale", subject, cfg["cleaning"])
    assert crit["tier"] == "T2" and len(kept) == 4


def test_furnished_rent_adjusted(cfg):
    subject = {"built_up": 1000, "property_type": "Condominium"}
    comps = [_comp(i, 3000 + i * 20, 1000, furn="fully" if i == 1 else "", beds=None) for i in range(1, 5)]
    kept, _, _ = cleaning.select_comparables(comps, "rent", subject, cfg["cleaning"])
    k1 = next(c for c in kept if c["id"] == "1")
    assert k1["adj_price"] == round(3020 * 0.9) and "furnished" in k1["match"]


def test_area_scope_requires_known_type(cfg):
    subject = {"built_up": 1000, "property_type": "Condominium"}
    comps = [_comp(1, 500000, 1000, ptype="", title="Nice unit", beds=None)]
    kept, removed, _ = cleaning.select_comparables(comps, "sale", subject, cfg["cleaning"], "area")
    assert not kept and "type not stated" in removed[0]["reason"]


def test_subject_bedrooms_parsed():
    t = telegram.parse_post_listings({"channel": "trinity", "post_id": 9, "text": TRINITY + "\nBedroom: 3 Rooms"})
    assert t[0].bedrooms == 3


def test_floor_is_not_a_building():
    assert bpl.derive_building("Unit No., 28th Floor, Kiara 1888, Jalan Kiara, 50480, Kuala Lumpur", "") == "Kiara 1888"


def test_condo_serviced_labels_merge_only_within_building(cfg):
    subject = {"built_up": 1100, "property_type": "Service Apartment", "bedrooms": 3}
    comps = [_comp(1, 500000, 1100, ptype="Condominium"), _comp(2, 505000, 1100, ptype="Service Residence"),
             _comp(3, 510000, 1120, ptype="Condominium"), _comp(4, 498000, 1090, ptype="Service Residence")]
    kept, _, _ = cleaning.select_comparables(comps, "sale", subject, cfg["cleaning"], "building")
    assert len(kept) == 4
    kept, removed, _ = cleaning.select_comparables(comps, "sale", subject, cfg["cleaning"], "area")
    assert {c["id"] for c in kept} == {"2", "4"}


def test_building_match_is_strict():
    assert not portals.matches_building({"title": "Royal Lexis", "address": "Jalan Sultan Ismail, KL"}, "Royal Tower")
    assert portals.matches_building({"title": "Royal Tower", "address": "Mont Kiara, Kuala Lumpur"}, "Royal Tower")
    assert not portals.matches_building({"title": "Royal Tower", "address": "Danga Bay, Johor Bahru"},
                                        "Royal Tower", "Kuala Lumpur")
    assert portals.matches_building({"title": "Danau Kota Suites Setapak"}, "Residensi Danau Kota Suites")


def test_search_names_and_block_suffix_match():
    assert portals.search_names("Casa Kiara (BLK-B)") == ["Casa Kiara"]
    assert portals.search_names("Residensi M Vertika") == ["Residensi M Vertika", "M Vertika"]
    assert portals.matches_building({"title": "Casa Kiara", "address": "Mont Kiara, Kuala Lumpur"}, "Casa Kiara (BLK-B)")
    assert portals.matches_building({"title": "M Vertika", "address": "Cheras, Kuala Lumpur"}, "Residensi M Vertika")
    assert not portals.matches_building({"title": "M Centura", "address": "Cheras"}, "Residensi M Vertika")


# ------------------------------------------------------------------ Lowyat ----
from auction_tracker import forum

DDG_PAGE = ('<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fforum.lowyat.net%2Ftopic%2F4512345'
            '%2F%2B40&rut=x">Parc 3 Cheras discussion</a><a href="https://forum.lowyat.net/topic/4512345">dup</a>'
            '<a href="https://forum.lowyat.net/topic/999">other</a>')
THREAD_PAGE = """<html><head><title>Parc 3 @ Cheras owners & tenants - Lowyat.NET</title></head><body>
<table><tr><td><span class="postdetails">Sep 12 2026, 10:01 PM</span>
<div class="postcolor">Water supply problem again this week, the lifts also always down. Management very slow to respond.</div></td></tr></table>
<table><tr><td><span class="postdetails">Sep 20 2026, 08:00 AM</span>
<div class="postcolor"><div class="quotemain">quoted text should be skipped water</div>Easy to rent, my tenant pays 3.3k, high demand from expats near the MRT.</div></td></tr></table>
<table><tr><td><div class="postcolor">hello</div></td></tr></table>
<a href="/topic/4512345/+20">2</a><a href="/topic/4512345/+40">3</a></body></html>"""


def test_lowyat_links_and_thread_parsing():
    assert forum.topic_links(DDG_PAGE) == ["https://forum.lowyat.net/topic/4512345", "https://forum.lowyat.net/topic/999"]
    t = forum.parse_thread(THREAD_PAGE, "https://forum.lowyat.net/topic/4512345")
    assert t["title"] == "Parc 3 @ Cheras owners & tenants" and t["last_offset"] == 40
    assert len(t["posts"]) == 2 and "quoted" not in t["posts"][1]["text"]
    topics, tone = forum.classify(t["posts"][0]["text"])
    assert {"water", "lifts", "management"} <= set(topics) and tone == "negative"
    topics, tone = forum.classify(t["posts"][1]["text"])
    assert "rental demand" in topics and tone == "positive"


def test_lowyat_collect_and_flag(cfg):
    class F:
        def get(self, url):
            if "duckduckgo" in url:
                return DDG_PAGE
            return THREAD_PAGE
    data = forum.collect(F(), "Parc 3", max_threads=1)
    assert data["threads"][0]["title"].startswith("Parc 3") and data["snippets"][0]["tone"] == "negative"
    data["snippets"].append({**data["snippets"][0], "text": "flood again, water leak in lobby"})
    summ = forum.summary(data)
    lst = {"built_up": 1100, "reserve_price": 400000, "auction_date": None, "flags": [], "dual_key": False}
    ev = scoring.evaluate(lst, None, None, None, {"rounds": 1}, None, {}, cfg, {"forum": summ})
    assert any("Lowyat owners/tenants repeatedly complain about water" in c for c in ev["cons"])


def test_valuation_uses_lower_quartile_and_cheapest(cfg):
    kept = [{"price": p, "built_up": 1000, "psf": p / 1000, "url": f"u{p}"} for p in (400000, 450000, 500000, 550000, 600000)]
    s = cleaning.summarize(kept, 1000, "sale", cfg["cleaning"])
    hc = 1 - cfg["cleaning"]["sale_asking_haircut"]
    assert s["estimate"] == round(450000 * hc) and s["cheapest_equiv"] == round(400000 * hc)


def test_rental_demand_and_resale_scores():
    sale = {"median_psf": 400, "n": 10}
    rent = {"median_psf": 2.2, "n": 9}
    pts, pros, _ = scoring.rental_demand(sale, rent, {"area_rent_psf": 2.0}, 1100, 400, 800)
    assert pts == 15 and any("yield" in p for p in pros)
    pts, pros, _ = scoring.resale_potential({"tenure": "Freehold"}, sale,
                                            {"built_year": date.today().year - 3, "area_sale_psf": 480,
                                             "trend": {"pct": 0.05, "days": 90}})
    assert pts == 10


def test_same_auction_different_names_merge():
    base = dict(area_label="Cheras", built_up=1453.0, reserve_price=729000.0, auction_date="2026-10-07",
                dual_key=False, occupied=False, flags=[], address="", unit="", tenure="")
    rows = [{**base, "listing_id": "a", "url": "bpl", "source": "bplelonglist", "building": "Parc 3",
             "building_key": "parc 3"},
            {**base, "listing_id": "b", "url": "tg", "source": "telegram:x",
             "building": "Residensi Pudu Alam Rekreasi (Parc 3)", "building_key": "pudu alam rekreasi parc 3"}]
    out = pipeline.merge_cross_listed(rows)
    assert len(out) == 1 and out[0]["also_listed"]
